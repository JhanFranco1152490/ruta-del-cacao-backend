import copy

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from apps.common.territorial import coordinates_outside_operating_area

from ..exceptions import (
    DuplicateFarmName,
    FarmHasRecords,
    FarmIdConflict,
    FarmNotFound,
    InvalidCoordinates,
    LocationOutsideOperatingArea,
    MunicipalityDepartmentMismatch,
    ProducerRequired,
    StaleFarmVersion,
)
from ..models import MUNICIPALITY_DEPARTMENT_MISMATCH, Farm, FarmAuditEvent
from .audit import record_farm_audit_event
from .scope import readable_farms

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
        # Solo el nombre: el municipio tiene su propio filtro y los detalles no se buscan.
        farms = farms.filter(name__unaccent__icontains=term)
    return farms


def list_farms(actor, *, search=None, producer=None, municipality=None) -> QuerySet[Farm]:
    # Activas primero: la lista llega paginada, así que solo el servidor puede dejar las
    # inactivas al final de todas las páginas.
    return filter_farms(
        readable_farms(actor), search=search, producer=producer, municipality=municipality
    ).order_by("-is_active", "name_normalized", "id")


def get_farm(actor, farm_id) -> Farm:
    try:
        return readable_farms(actor).get(pk=farm_id)
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
            return _resent_farm(existing, actor, data), False
        if _constraint_name(error) == NAME_UNIQUE_CONSTRAINT:
            raise DuplicateFarmName() from None
        raise
    record_farm_audit_event(farm=farm, actor=actor, action=FarmAuditEvent.Action.CREATED)
    return farm, True


@transaction.atomic
def update_farm(actor, farm_id, expected_version: int, data: dict) -> Farm:
    try:
        farm = Farm.objects.select_for_update().get(pk=farm_id, producer_id=actor.producer_id)
    except Farm.DoesNotExist:
        raise FarmNotFound() from None
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


@transaction.atomic
def delete_farm(actor, farm_id, expected_version: int) -> None:
    """Elimina una finca creada por error. Solo si no tiene registros del negocio; la que los
    tiene se desactiva. Su auditoría se conserva y el borrado queda registrado en ella."""
    try:
        farm = Farm.objects.select_for_update().get(pk=farm_id, producer_id=actor.producer_id)
    except Farm.DoesNotExist:
        raise FarmNotFound() from None
    if farm.version != expected_version:
        raise StaleFarmVersion(farm)
    if _has_business_records(farm):
        raise FarmHasRecords()
    record_farm_audit_event(farm=farm, actor=actor, action=FarmAuditEvent.Action.DELETED)
    farm.delete()


def _has_business_records(farm: Farm) -> bool:
    # Cualquier tabla que apunte a la finca cuenta, salvo su auditoría: así una tabla nueva
    # (parcelas, capturas, cosechas) bloquea el borrado sin que nadie la agregue a una lista.
    # `include_hidden` incluye también las relaciones declaradas sin nombre inverso.
    for relation in Farm._meta.get_fields(include_hidden=True):
        if not relation.auto_created or relation.concrete:
            continue
        if relation.related_model is FarmAuditEvent:
            continue
        lookup = {relation.field.name: farm}
        if relation.related_model._base_manager.filter(**lookup).exists():
            return True
    return False


def _resent_farm(existing: Farm, actor, data: dict) -> Farm:
    if existing.producer_id != actor.producer_id:
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
