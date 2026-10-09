from collections.abc import Iterable
from decimal import Decimal

from django.contrib.auth.base_user import AbstractBaseUser

from ..models import AgriculturalInput, AgriculturalInputAuditEvent


def api_value(value):
    """El valor como lo ve la API: el peso en texto con dos decimales, el resto tal cual."""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return value


def record_input_audit_event(
    *,
    item: AgriculturalInput,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
    before: dict | None = None,
) -> AgriculturalInputAuditEvent:
    """Deja un evento con, por cada campo cambiado, su valor anterior y nuevo. Sin `before`
    (el alta), cada anterior es `None`."""
    before = before or {}
    fields = sorted(set(changed_fields))
    changes = {
        name: {"before": api_value(before.get(name)), "after": api_value(getattr(item, name))}
        for name in fields
    }
    return AgriculturalInputAuditEvent.record(
        input=item,
        input_ref=item.pk,
        input_name=item.name,
        actor=actor,
        action=action,
        changed_fields=fields,
        version=item.version,
        changes=changes,
    )
