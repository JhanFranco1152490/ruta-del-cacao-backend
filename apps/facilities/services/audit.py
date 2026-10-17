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
