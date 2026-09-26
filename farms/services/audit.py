from collections.abc import Iterable

from accounts.models import User

from ..models import Farm, FarmAuditEvent


def record_farm_audit_event(
    *,
    farm: Farm,
    actor: User,
    action: str,
    changed_fields: Iterable[str] = (),
) -> FarmAuditEvent:
    if action not in FarmAuditEvent.Action.values:
        raise ValueError("Unsupported farm audit action.")

    normalized_fields = sorted(set(changed_fields))
    if any(not isinstance(field, str) or not field for field in normalized_fields):
        raise ValueError("Changed fields must be non-empty strings.")

    return FarmAuditEvent.objects.create(
        farm=farm,
        actor=actor,
        action=action,
        changed_fields=normalized_fields,
    )
