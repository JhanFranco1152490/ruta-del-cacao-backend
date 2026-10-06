import copy
from decimal import Decimal
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, Q, QuerySet, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError as FieldError

from apps.common.audit import record_update_events
from apps.common.db import has_dependent_rows, save_translating_unique
from apps.common.farm_dependents import registered_dependents
from apps.common.ownership import owner_filter
from apps.common.territorial import coordinates_outside_operating_area
from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import (
    DuplicateFarmName,
    FarmAreaBelowPlots,
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
from ..validators import validate_altitude_for_municipality
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
# Lo que decide si la altitud cabe en el terreno: si ninguno cambia, no se vuelve a exigir.
ALTITUDE_FIELDS = frozenset({"altitude_masl", "municipality_code"})
# El área ya repartida en parcelas activas. Las parcelas se alcanzan por su relación con la finca
# (`plots`), sin importar su app: así esta app no depende del código de la otra.
ALLOCATED_AREA = Coalesce(
    Sum("plots__area_hectares", filter=Q(plots__is_active=True)),
    Value(Decimal("0")),
    output_field=DecimalField(max_digits=12, decimal_places=2),
)


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
    farms = readable_farms(actor).annotate(allocated_area_hectares=ALLOCATED_AREA)
    return filter_farms(
        farms, search=search, producer=producer, municipality=municipality
    ).order_by("-is_active", "name_normalized", "id")


def get_farm(actor, farm_id) -> Farm:
    try:
        return (
            readable_farms(actor).annotate(allocated_area_hectares=ALLOCATED_AREA).get(pk=farm_id)
        )
    except Farm.DoesNotExist:
        raise FarmNotFound() from None


def _target_producer(actor, data: dict):
    """El productor de la finca nueva: el de la sesión, o el que nombra la cuenta técnica.

    La cuenta técnica no tiene un productor propio, así que lo manda en `producer_id` (y debe
    existir y estar activo). Para cualquier otra cuenta mandarlo es un error, aunque sea el suyo:
    una finca nunca se crea a nombre de otro productor. Quita `producer_id` de `data`.
    """
    requested = data.pop("producer_id", None)
    if not actor.is_superuser:
        if requested is not None:
            raise FieldError({"producer_id": ["Campo no permitido."]})
        if actor.producer_id is None:
            raise ProducerRequired()
        return actor.producer_id
    if requested is None:
        raise FieldError({"producer_id": ["Este campo es requerido."]})
    # El modelo se toma de la relación y no de su app: ninguna app importa de otra.
    producer = Farm._meta.get_field("producer").related_model.objects.filter(pk=requested).first()
    if producer is None:
        raise FieldError({"producer_id": ["El productor no existe."]})
    if producer.status != "active":
        raise FieldError({"producer_id": ["El productor está inactivo."]})
    return producer.pk


@transaction.atomic
def create_farm(actor, data: dict) -> tuple[Farm, bool]:
    """Crea una finca y devuelve `(finca, creada)`.

    El cliente puede enviar el `id` que generó sin conexión. Reenviar el mismo `id` con el mismo
    contenido devuelve la finca ya creada (`creada=False`), de modo que reintentar un envío
    cortado nunca duplica.
    """
    producer_id = _target_producer(actor, data)
    farm_id = data.get("id")
    if farm_id is not None:
        existing = Farm.objects.filter(pk=farm_id).first()
        if existing is not None:
            return _resent_farm(existing, producer_id, data), False

    farm = Farm(producer_id=producer_id, **_without_empty_id(data))
    _validate(farm, check_operating_area=True, check_altitude=True)
    # Dos sincronizaciones simultáneas del mismo registro: la otra ganó la carrera.
    existing = save_translating_unique(
        lambda: farm.save(force_insert=True),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=DuplicateFarmName,
        find_existing=lambda: (
            Farm.objects.filter(pk=farm.pk).first() if farm_id is not None else None
        ),
    )
    if existing is not None:
        return _resent_farm(existing, producer_id, data), False
    record_farm_audit_event(farm=farm, actor=actor, action=FarmAuditEvent.Action.CREATED)
    farm.allocated_area_hectares = Decimal("0")
    return farm, True


@transaction.atomic
def update_farm(actor, farm_id, expected_version: int, data: dict) -> Farm:
    try:
        farm = Farm.objects.select_for_update().get(pk=farm_id, **owner_filter(actor))
    except Farm.DoesNotExist:
        raise FarmNotFound() from None
    # Con la finca bloqueada, ninguna parcela se registra ni se agranda hasta que esto termine.
    # La suma va en una consulta aparte: PostgreSQL no bloquea filas de una consulta agrupada.
    _set_allocated_area(farm)
    if check_expected_version(
        farm,
        expected_version,
        stale=lambda: StaleFarmVersion(farm),
        already_applied=lambda: _already_applied(farm, data),
    ):
        return farm

    before = {name: getattr(farm, name) for name in data}
    for name, value in data.items():
        setattr(farm, name, value)
    # El rectángulo de operación solo se exige si el punto se mueve: una finca guardada antes
    # de esa regla puede seguir corrigiendo sus otros datos.
    moved = any(data[name] != before[name] for name in COORDINATE_FIELDS & data.keys())
    # Igual con la altitud y el terreno del municipio: solo si cambia alguno de los dos.
    location_changed = any(data[name] != before[name] for name in ALTITUDE_FIELDS & data.keys())
    _validate(farm, check_operating_area=moved, check_altitude=location_changed)
    # Se compara después de validar: `clean()` recorta el nombre, y un nombre que solo cambió
    # en espacios no es un cambio real.
    changed = [name for name in data if getattr(farm, name) != before[name]]
    if not changed:
        return farm
    if "area_hectares" in changed and farm.area_hectares < farm.allocated_area_hectares:
        raise FarmAreaBelowPlots(farm.allocated_area_hectares)

    update_fields = [*changed, "name_normalized"] if "name" in changed else changed
    save_next_version(
        farm, update_fields, constraint=NAME_UNIQUE_CONSTRAINT, duplicate=DuplicateFarmName
    )
    record_update_events(
        partial(record_farm_audit_event, farm=farm, actor=actor),
        changed,
        updated=FarmAuditEvent.Action.UPDATED,
        status_changed=FarmAuditEvent.Action.STATUS_CHANGED,
    )
    return farm


@transaction.atomic
def delete_farm(actor, farm_id, expected_version: int) -> None:
    """Elimina una finca creada por error. Solo si no tiene registros del negocio; la que los
    tiene se desactiva. Su auditoría se conserva y el borrado queda registrado en ella."""
    try:
        farm = Farm.objects.select_for_update().get(pk=farm_id, **owner_filter(actor))
    except Farm.DoesNotExist:
        raise FarmNotFound() from None
    check_expected_version(farm, expected_version, stale=lambda: _stale_with_allocated_area(farm))
    remove_unimportant_farm(farm, actor)


def remove_unimportant_farm(farm: Farm, actor) -> None:
    """Elimina `farm` con lo que depende de ella si nada de eso es importante; si lo es,
    `FarmHasRecords` y no se toca nada. Quien llama ya validó quién puede hacerlo: aquí solo se
    aplica la regla y se deja el rastro."""
    if has_business_records(farm):
        raise FarmHasRecords()
    for dependent in registered_dependents():
        dependent.delete_all(farm, actor)
    record_farm_audit_event(farm=farm, actor=actor, action=FarmAuditEvent.Action.DELETED)
    farm.delete()


def has_business_records(farm: Farm) -> bool:
    """Si la finca tiene algo importante: un dependiente registrado (sus parcelas) que lo
    considere así, o cualquier otra tabla que la apunte, salvo su auditoría. Así una tabla nueva
    (capturas, cosechas) bloquea el borrado sin que nadie la agregue a una lista."""
    dependents = registered_dependents()
    if any(dependent.important_record(farm) for dependent in dependents):
        return True
    handled = tuple(model for dependent in dependents for model in dependent.models)
    return has_dependent_rows(farm, ignore=(FarmAuditEvent, *handled))


def _resent_farm(existing: Farm, producer_id, data: dict) -> Farm:
    if existing.producer_id != producer_id:
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


def _stale_with_allocated_area(farm: Farm) -> StaleFarmVersion:
    # El conflicto devuelve la finca del servidor, con su área asignada como en toda respuesta de
    # una finca.
    _set_allocated_area(farm)
    return StaleFarmVersion(farm)


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


def _validate(farm: Farm, *, check_operating_area: bool, check_altitude: bool) -> None:
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
    if check_altitude:
        validate_altitude_for_municipality(farm.altitude_masl, farm.municipality_code)


def _without_empty_id(data: dict) -> dict:
    return {name: value for name, value in data.items() if name != "id" or value is not None}
