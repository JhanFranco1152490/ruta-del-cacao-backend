import copy
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from apps.common.db import constraint_name
from apps.common.municipalities import municipality_codes_matching

from ..exceptions import (
    DuplicateFarmName,
    FarmAreaBelowPlots,
    FarmIdConflict,
    FarmNotFound,
    InvalidCoordinates,
    MunicipalityDepartmentMismatch,
    ProducerRequired,
    StaleFarmVersion,
)
from ..models import MUNICIPALITY_DEPARTMENT_MISMATCH, Farm, FarmAuditEvent
from .audit import record_farm_audit_event

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
# El área ya repartida en parcelas activas. Las parcelas se alcanzan por su relación con la finca
# (`plots`), sin importar su app: así esta app no depende del código de la otra.
ALLOCATED_AREA = Coalesce(
    Sum("plots__area_hectares", filter=Q(plots__is_active=True)),
    Value(Decimal("0")),
    output_field=DecimalField(max_digits=12, decimal_places=2),
)


def list_farms(actor, search: str | None = None) -> QuerySet[Farm]:
    farms = (
        Farm.objects.filter(producer_id=actor.producer_id)
        .annotate(allocated_area_hectares=ALLOCATED_AREA)
        .order_by("name_normalized", "id")
    )
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


def get_farm(actor, farm_id) -> Farm:
    try:
        return Farm.objects.annotate(allocated_area_hectares=ALLOCATED_AREA).get(
            pk=farm_id, producer_id=actor.producer_id
        )
    except Farm.DoesNotExist:
        raise FarmNotFound() from None


@transaction.atomic
def create_farm(actor, data: dict) -> tuple[Farm, bool]:
    """Crea la finca del productor de la sesión. Devuelve `(finca, creada)`.

    El cliente puede enviar el `id` que generó sin conexión. Reenviar el mismo `id` con el mismo
    contenido devuelve la finca ya creada (`creada=False`), de modo que reintentar un envío
    cortado nunca duplica.
    """
    if actor.producer_id is None:
        raise ProducerRequired()
    farm_id = data.get("id")
    if farm_id is not None:
        existing = Farm.objects.filter(pk=farm_id).first()
        if existing is not None:
            return _resent_farm(existing, actor, data), False

    farm = Farm(producer_id=actor.producer_id, **_without_empty_id(data))
    _validate(farm)
    try:
        with transaction.atomic():
            farm.save(force_insert=True)
    except IntegrityError as error:
        # Dos sincronizaciones simultáneas del mismo registro: la otra ganó la carrera. Según
        # el orden en que PostgreSQL revise los índices, el choque puede reportarse en la
        # clave primaria o en el nombre, así que se decide mirando si el id ya existe.
        existing = Farm.objects.filter(pk=farm.pk).first() if farm_id is not None else None
        if existing is not None:
            return _resent_farm(existing, actor, data), False
        if constraint_name(error) == NAME_UNIQUE_CONSTRAINT:
            raise DuplicateFarmName() from None
        raise
    record_farm_audit_event(farm=farm, actor=actor, action=FarmAuditEvent.Action.CREATED)
    farm.allocated_area_hectares = Decimal("0")
    return farm, True


@transaction.atomic
def update_farm(actor, farm_id, expected_version: int, data: dict) -> Farm:
    try:
        farm = Farm.objects.select_for_update().get(pk=farm_id, producer_id=actor.producer_id)
    except Farm.DoesNotExist:
        raise FarmNotFound() from None
    # Con la finca bloqueada, ninguna parcela se registra ni se agranda hasta que esto termine.
    # La suma va en una consulta aparte: PostgreSQL no bloquea filas de una consulta agrupada.
    _set_allocated_area(farm)
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
    _validate(farm)
    # Se compara después de validar: `clean()` recorta el nombre, y un nombre que solo cambió
    # en espacios no es un cambio real.
    changed = [name for name in data if getattr(farm, name) != before[name]]
    if not changed:
        return farm
    if "area_hectares" in changed and farm.area_hectares < farm.allocated_area_hectares:
        raise FarmAreaBelowPlots(farm.allocated_area_hectares)

    farm.version += 1
    update_fields = [*changed, "version", "updated_at"]
    if "name" in changed:
        update_fields.append("name_normalized")
    try:
        with transaction.atomic():
            farm.save(update_fields=update_fields)
    except IntegrityError as error:
        if constraint_name(error) == NAME_UNIQUE_CONSTRAINT:
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


def _resent_farm(existing: Farm, actor, data: dict) -> Farm:
    if existing.producer_id != actor.producer_id:
        raise FarmIdConflict()
    _set_allocated_area(existing)
    # Con el mismo dueño, un contenido distinto suele ser un pendiente editado en el dispositivo
    # después de una creación cuya respuesta se perdió. El conflicto lleva la finca del servidor
    # para que el cliente envíe esa edición como un PATCH con su versión, en vez de quedar
    # trabado reenviando un POST que siempre chocaría.
    if not _matches(existing, data, CONTENT_FIELDS):
        raise FarmIdConflict(existing)
    return existing


def _set_allocated_area(farm: Farm) -> None:
    farm.allocated_area_hectares = Farm.objects.filter(pk=farm.pk).aggregate(
        allocated=ALLOCATED_AREA
    )["allocated"]


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


def _validate(farm: Farm) -> None:
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


def _without_empty_id(data: dict) -> dict:
    return {name: value for name, value in data.items() if name != "id" or value is not None}
