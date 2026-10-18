from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from apps.common.audit import field_changes

from ..models import PostharvestFacility, PostharvestFacilityAuditEvent


def record_facility_audit_event(
    *,
    facility: PostharvestFacility,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
    before: dict | None = None,
) -> PostharvestFacilityAuditEvent:
    """Deja un evento con, por cada campo cambiado, su valor anterior y nuevo. Sin `before`
    (el alta), cada anterior es `None`."""
    fields = sorted(set(changed_fields))
    changes = field_changes(
        before or {},
        {name: getattr(facility, name) for name in fields},
        fields=fields,
    )
    return _record(facility, actor, action, fields, changes)


def record_occupancy_event(
    *, facility: PostharvestFacility, actor: AbstractBaseUser, action: str, before_lot, after_lot
) -> PostharvestFacilityAuditEvent:
    """Deja la entrada o la salida de un lote, que se guarda por su id como lo nombra la API."""
    changes = field_changes(
        {"current_lot": before_lot.pk if before_lot is not None else None},
        {"current_lot": after_lot.pk if after_lot is not None else None},
    )
    return _record(facility, actor, action, ["current_lot"], changes)


def _record(facility, actor, action, fields, changes) -> PostharvestFacilityAuditEvent:
    return PostharvestFacilityAuditEvent.record(
        facility=facility,
        facility_ref=facility.pk,
        facility_name=facility.name,
        farm_ref=facility.farm_id,
        actor=actor,
        action=action,
        changed_fields=fields,
        version=facility.version,
        changes=changes,
    )
