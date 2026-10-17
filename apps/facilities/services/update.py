import copy
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common.audit import record_update_events
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import FacilityFieldsLocked, FacilityNotFound, StaleFacilityVersion
from ..models import PostharvestFacility, PostharvestFacilityAuditEvent
from ..usage import is_used
from .audit import record_facility_audit_event
from .create import CONTENT_FIELDS, NAME_UNIQUE_CONSTRAINT, duplicate_error

# Cambiarlo haría que los procesos en los que se usó dijeran otra cosa: un cajón que fermentó un
# lote no pasa a ser marquesina. El nombre y la capacidad no cambian lo que significa un proceso.
LOCKED_WHEN_USED = ("facility_type",)


@transaction.atomic
def update_facility(actor, facility_id, expected_version: int, data: dict) -> PostharvestFacility:
    """Edita un cajón o una marquesina, incluida su activación o desactivación. La finca no se
    edita. Sin cambios reales devuelve el elemento tal cual, sin subir la versión ni dejar
    historial."""
    facility, _farm = lock_aggregate_root(
        PostharvestFacility,
        facility_id,
        root="farm",
        scope=owner_filter(actor, "farm__producer_id", farm="farm_id"),
        not_found=FacilityNotFound,
    )

    if check_expected_version(
        facility,
        expected_version,
        stale=lambda: StaleFacilityVersion(_with_usage(facility)),
        already_applied=lambda: _already_applied(facility, data),
    ):
        return _with_usage(facility)

    before = {name: getattr(facility, name) for name in CONTENT_FIELDS}
    _apply(facility, data)
    facility.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    # Se compara después de validar: un nombre que solo cambió en espacios no es un cambio.
    changed = [name for name in CONTENT_FIELDS if getattr(facility, name) != before[name]]
    if not changed:
        return _with_usage(facility)

    used = is_used(facility)
    for name in LOCKED_WHEN_USED:
        if used and name in changed:
            raise FacilityFieldsLocked(name)

    update_fields = [*changed, "name_normalized"] if "name" in changed else changed
    save_next_version(
        facility,
        update_fields,
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=lambda: duplicate_error(facility),
    )
    record_update_events(
        partial(record_facility_audit_event, facility=facility, actor=actor, before=before),
        changed,
        updated=PostharvestFacilityAuditEvent.Action.UPDATED,
        status_changed=PostharvestFacilityAuditEvent.Action.STATUS_CHANGED,
    )
    facility.has_records = used
    return facility


def _apply(facility: PostharvestFacility, data: dict) -> None:
    for name, value in data.items():
        setattr(facility, name, value)


def _already_applied(facility: PostharvestFacility, data: dict) -> bool:
    """Si el elemento ya tiene lo que se pide: un doble clic reintenta aunque el servidor haya
    aplicado el cambio. Se compara después de limpiar como al guardar."""
    candidate = copy.copy(facility)
    _apply(candidate, data)
    try:
        candidate.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    except ValidationError:
        return False
    return all(getattr(candidate, name) == getattr(facility, name) for name in CONTENT_FIELDS)


def _with_usage(facility: PostharvestFacility) -> PostharvestFacility:
    facility.has_records = is_used(facility)
    return facility
