import copy
import unicodedata

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from apps.common.municipalities import MUNICIPALITIES_BY_CODE
from apps.common.territorial import (
    InvalidDepartmentCode,
    InvalidMunicipalityCode,
    validate_municipality_department,
)
from apps.common.territorial import (
    MunicipalityDepartmentMismatch as TerritorialMismatch,
)

from ..exceptions import (
    DuplicateFarmName,
    FarmIdConflict,
    FarmNotFound,
    InvalidCoordinates,
    MunicipalityDepartmentMismatch,
    ProducerRequired,
    StaleFarmVersion,
)
from ..models import Farm, FarmAuditEvent
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


def list_farms(actor, search: str | None = None) -> QuerySet[Farm]:
    farms = Farm.objects.filter(producer_id=actor.producer_id).order_by("name_normalized", "id")
    term = (search or "").strip()
    if term:
        farms = farms.filter(
            Q(name__unaccent__icontains=term)
            | Q(details__unaccent__icontains=term)
            | Q(municipality_code__in=_municipality_codes_matching(term))
        )
    return farms


def get_farm(actor, farm_id) -> Farm:
    try:
        return Farm.objects.get(pk=farm_id, producer_id=actor.producer_id)
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
    _validate(farm)
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


def _resent_farm(existing: Farm, actor, data: dict) -> Farm:
    if existing.producer_id != actor.producer_id:
        raise FarmIdConflict()
    candidate = Farm(producer_id=actor.producer_id, **data)
    try:
        candidate.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError:
        raise FarmIdConflict() from None
    if any(getattr(candidate, name) != getattr(existing, name) for name in CONTENT_FIELDS):
        raise FarmIdConflict()
    return existing


def _already_applied(farm: Farm, data: dict) -> bool:
    candidate = copy.copy(farm)
    for name, value in data.items():
        setattr(candidate, name, value)
    try:
        candidate.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError:
        return False
    return all(getattr(candidate, name) == getattr(farm, name) for name in data)


def _validate(farm: Farm) -> None:
    try:
        validate_municipality_department(farm.municipality_code, farm.department_code)
    except TerritorialMismatch:
        raise MunicipalityDepartmentMismatch() from None
    except (InvalidDepartmentCode, InvalidMunicipalityCode):
        # Códigos inexistentes: los informa full_clean() como error de campo.
        pass

    try:
        farm.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as error:
        errors = error.message_dict
        if errors.keys() <= COORDINATE_FIELDS:
            raise InvalidCoordinates(fields=errors) from None
        raise


def _without_empty_id(data: dict) -> dict:
    return {name: value for name, value in data.items() if name != "id" or value is not None}


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def _municipality_codes_matching(term: str) -> list[str]:
    # El municipio se guarda como código; su nombre vive en el catálogo en memoria, así que la
    # búsqueda por nombre se traduce aquí a los códigos que coinciden.
    folded = _fold(term)
    return [code for code, name in MUNICIPALITIES_BY_CODE.items() if folded in _fold(name)]
