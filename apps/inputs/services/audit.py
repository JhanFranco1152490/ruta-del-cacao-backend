from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from apps.common.audit import field_changes

from ..models import AgriculturalInput, AgriculturalInputAuditEvent

# Como los muestra la API del insumo: el contenido del empaque con tres decimales.
DECIMAL_PLACES = 3


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
    fields = sorted(set(changed_fields))
    changes = field_changes(
        before or {},
        {name: getattr(item, name) for name in fields},
        fields=fields,
        decimal_places=DECIMAL_PLACES,
    )
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
