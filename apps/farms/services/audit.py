from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from ..models import Farm, FarmAuditEvent


def record_farm_audit_event(
    *,
    farm: Farm,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
) -> FarmAuditEvent:
    return FarmAuditEvent.record(
        farm=farm, actor=actor, action=action, changed_fields=changed_fields
    )
