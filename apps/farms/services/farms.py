import copy

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from apps.common.municipalities import municipality_codes_matching
from apps.common.territorial import coordinates_outside_operating_area

from ..exceptions import (
    DuplicateFarmName,
    FarmIdConflict,
    FarmNotFound,
    InvalidCoordinates,
    LocationOutsideOperatingArea,
    MunicipalityDepartmentMismatch,
    ProducerAccessDenied,
    ProducerRequired,
    StaleFarmVersion,
)
from ..models import MUNICIPALITY_DEPARTMENT_MISMATCH, Farm, FarmAuditEvent
from .audit import record_farm_audit_event
from .scope import (
    can_manage_producer,
    managed_farms,
    producer_model,
    readable_farms,
    reads_every_producer,
)

NAME_UNIQUE_CONSTRAINT = "farms_producer_name_normalized_unique"
# Lo que describe a la finca. Dos envíos con el mismo id se consideran el mismo registro solo
# si todos estos campos coinciden.
CONTENT_FIELDS = (
    "name",
    "department_code",
    "municipality_code",
    "details",
    "area_hectares",
    "altitude_masl",
    "latitude",
    "longitude",
)
COORDINATE_FIELDS = frozenset({"latitude", "longitude"})


def filter_farms(farms, *, search=None, producer=None, municipality=None) -> QuerySet[Farm]:
    """Los filtros comunes del listado y del mapa, siempre dentro del alcance ya aplicado."""
    if producer is not None:
        farms = farms.filter(producer_id=producer)
    if municipality is not None:
        farms = farms.filter(municipality_code=municipality)
    term = (search or "").strip()
    if term:
        farms = farms.filter(
            Q(name__unaccent__icontains=term)
            | Q(details__unaccent__icontains=term)
            # El municipio se guarda como código; su nombre vive en el catálogo en memoria, así
            # que la búsqueda por nombre se traduce a los códigos que coinciden.
            | Q(municipality_code__in=municipality_codes_matching(term))
        )
    return farms


def scoped_farms(actor, *, search=None, producer=None, municipality=None) -> QuerySet[Farm]:
    """Lo que `actor` puede consultar, con los filtros del listado y del mapa."""
    # El alcance ya impide ver fincas ajenas; además se rechaza el filtro por otro productor
    # para que un intento así no pase como una consulta normal con la lista vacía.
    if producer is not None and not reads_every_producer(actor) and producer != actor.producer_id:
        raise ProducerAccessDenied()
    return filter_farms(
        readable_farms(actor), search=search, producer=producer, municipality=municipality
    )


def list_farms(actor, **filters) -> QuerySet[Farm]:
    return scoped_farms(actor, **filters).order_by("name_normalized", "id")


def get_farm(actor, farm_id) -> Farm:
    try:
        return readable_farms(actor).get(pk=farm_id)
    except Farm.DoesNotExist:
        raise FarmNotFound() from None


@transaction.atomic
def create_farm(actor, data: dict) -> tuple[Farm, bool]:
    """Crea una finca y devuelve `(finca, creada)`. Es del productor de la sesión o, si quien
    la crea es de la asociación, del productor que indica `producer_id`.

    El cliente puede enviar el `id` que generó sin conexión. Reenviar el mismo `id` con el mismo
    contenido devuelve la finca ya creada (`creada=False`), de modo que reintentar un envío
    cortado nunca duplica.
    """
    data = dict(data)
    producer_id = _producer_for_new_farm(actor, data.pop("producer_id", None))
    farm_id = data.get("id")
    if farm_id is not None:
        existing = Farm.objects.filter(pk=farm_id).first()
        if existing is not None:
            return _resent_farm(existing, producer_id, data), False

    farm = Farm(producer_id=producer_id, **_without_empty_id(data))
    _validate(farm, check_operating_area=True)
    try:
        with transaction.atomic():
            farm.save(force_insert=True)
    except IntegrityError as error:
        # Dos sincronizaciones simultáneas del mismo registro: la otra ganó la carrera. Según
        # el orden en que PostgreSQL revise los índices, el choque puede reportarse en la
        # clave primaria o en el nombre, así que se decide mirando si el id ya existe.
        existing = Farm.objects.filter(pk=farm.pk).first() if farm_id is not None else None
        if existing is not None:
            return _resent_farm(existing, producer_id, data), False
        if _constraint_name(error) == NAME_UNIQUE_CONSTRAINT:
            raise DuplicateFarmName() from None
        raise
    record_farm_audit_event(farm=farm, actor=actor, action=FarmAuditEvent.Action.CREATED)
    return farm, True


@transaction.atomic
def update_farm(actor, farm_id, expected_version: int, data: dict) -> Farm:
    farm = _lock_managed_farm(actor, farm_id)
    if farm.version != expected_version:
        # Una cola sin conexión reintenta cuando no recibió la respuesta, aunque el servidor sí
        # haya aplicado el cambio. Si la finca ya tiene justo lo que se pide, el resultado sería
        # el mismo: se responde como éxito en vez de mandar esa edición a revisión manual.
        if _already_applied(farm, data):
            return farm
        raise StaleFarmVersion(farm)

    before = {name: getattr(farm, name) for name in data}
    for name, value in data.items():
        setattr(farm, name, value)
    # El rectángulo de operación solo se exige si el punto se mueve: una finca guardada antes
    # de esa regla puede seguir corrigiendo sus otros datos.
    moved = any(data[name] != before[name] for name in COORDINATE_FIELDS & data.keys())
    _validate(farm, check_operating_area=moved)
    # Se compara después de validar: `clean()` recorta el nombre, y un nombre que solo cambió
    # en espacios no es un cambio real.
    changed = [name for name in data if getattr(farm, name) != before[name]]
    if not changed:
        return farm

    farm.version += 1
    update_fields = [*changed, "version", "updated_at"]
    if "name" in changed:
        update_fields.append("name_normalized")
    try:
        with transaction.atomic():
            farm.save(update_fields=update_fields)
    except IntegrityError as error:
        if _constraint_name(error) == NAME_UNIQUE_CONSTRAINT:
            raise DuplicateFarmName() from None
        raise

    content_changes = [name for name in changed if name != "is_active"]
    if content_changes:
        record_farm_audit_event(
            farm=farm,
            actor=actor,
            action=FarmAuditEvent.Action.UPDATED,
            changed_fields=content_changes,
        )
    if "is_active" in changed:
        record_farm_audit_event(
            farm=farm,
            actor=actor,
            action=FarmAuditEvent.Action.STATUS_CHANGED,
            changed_fields=["is_active"],
        )
    return farm


def _producer_for_new_farm(actor, requested_producer_id):
    if reads_every_producer(actor):
        # La asociación no tiene productor propio: siempre dice para cuál crea.
        if requested_producer_id is None:
            raise ValidationError({"producer_id": ["Indica el productor de la finca."]})
        if not producer_model().objects.filter(pk=requested_producer_id).exists():
            raise ValidationError({"producer_id": ["El productor no existe."]})
        if not can_manage_producer(actor, requested_producer_id):
            raise ProducerAccessDenied()
        return requested_producer_id
    if actor.producer_id is None:
        raise ProducerRequired()
    if requested_producer_id is not None and requested_producer_id != actor.producer_id:
        raise ProducerAccessDenied()
    return actor.producer_id


def _lock_managed_farm(actor, farm_id) -> Farm:
    try:
        # `of=("self",)`: solo se bloquea la fila de la finca, no las del productor o el
        # interruptor que entran en la consulta para decidir si se puede gestionar.
        return managed_farms(actor).select_for_update(of=("self",)).get(pk=farm_id)
    except Farm.DoesNotExist:
        pass
    # La asociación ve fincas que no puede gestionar (interruptor apagado): eso es falta de
    # permiso, no una finca inexistente.
    if readable_farms(actor).filter(pk=farm_id).exists():
        raise ProducerAccessDenied()
    raise FarmNotFound()


def _resent_farm(existing: Farm, producer_id, data: dict) -> Farm:
    if existing.producer_id != producer_id:
        raise FarmIdConflict()
    # Con el mismo dueño, un contenido distinto suele ser un pendiente editado en el dispositivo
    # después de una creación cuya respuesta se perdió. El conflicto lleva la finca del servidor
    # para que el cliente envíe esa edición como un PATCH con su versión, en vez de quedar
    # trabado reenviando un POST que siempre chocaría.
    if not _matches(existing, data, CONTENT_FIELDS):
        raise FarmIdConflict(existing)
    return existing


def _already_applied(farm: Farm, data: dict) -> bool:
    return _matches(farm, data, data)


def _matches(farm: Farm, data: dict, fields) -> bool:
    # Se compara después de limpiar los datos como al guardarlos: "12.5" y "12.50" o un nombre
    # con espacios alrededor no son contenido distinto.
    candidate = copy.copy(farm)
    for name, value in data.items():
        setattr(candidate, name, value)
    try:
        candidate.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError:
        return False
    return all(getattr(candidate, name) == getattr(farm, name) for name in fields)


def _validate(farm: Farm, *, check_operating_area: bool) -> None:
    try:
        farm.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as error:
        municipality_errors = error.error_dict.get("municipality_code", [])
        if any(item.code == MUNICIPALITY_DEPARTMENT_MISMATCH for item in municipality_errors):
            raise MunicipalityDepartmentMismatch() from None
        errors = error.message_dict
        if errors.keys() <= COORDINATE_FIELDS:
            raise InvalidCoordinates(fields=errors) from None
        raise
    # Después de full_clean(): una coordenada imposible (latitud 95) se informa como
    # `invalid_coordinates`, no como un punto fuera de Norte de Santander.
    if check_operating_area:
        outside = coordinates_outside_operating_area(farm.latitude, farm.longitude)
        if outside:
            raise LocationOutsideOperatingArea(
                fields={name: ["Debe estar dentro de Norte de Santander."] for name in outside}
            )


def _without_empty_id(data: dict) -> dict:
    return {name: value for name, value in data.items() if name != "id" or value is not None}


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)
