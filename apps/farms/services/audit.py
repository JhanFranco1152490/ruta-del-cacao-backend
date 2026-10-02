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
    if action not in FarmAuditEvent.Action.values:
        raise ValueError("Unsupported farm audit action.")

    normalized_fields = sorted(set(changed_fields))
    if any(not isinstance(field, str) or not field for field in normalized_fields):
        raise ValueError("Changed fields must be non-empty strings.")

    return FarmAuditEvent.objects.create(
        farm=farm,
        farm_ref=farm.pk,
        farm_name=farm.name,
        actor=actor,
        action=action,
        changed_fields=normalized_fields,
    )
