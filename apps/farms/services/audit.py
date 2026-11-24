from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from apps.common.audit import record_changes

from ..models import Farm, FarmAuditEvent

# Lo que la bitácora muestra con su valor. Ninguno es un dato personal.
VALUE_FIELDS = (
    "name",
    "municipality_code",
    "area_hectares",
    "altitude_masl",
    "latitude",
    "longitude",
    "details",
    "is_active",
)


def record_farm_audit_event(
    *,
    farm: Farm,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
    before: dict | None = None,
) -> FarmAuditEvent:
    """Deja el evento con los campos que cambiaron y su valor anterior y nuevo (`before` es lo que
    tenía la finca antes de una edición)."""
    changed_fields = list(changed_fields)
    return FarmAuditEvent.record(
        farm=farm,
        farm_ref=farm.pk,
        farm_name=farm.name,
        producer_ref=farm.producer_id,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        changes=record_changes(
            farm,
            value_fields=VALUE_FIELDS,
            changed_fields=changed_fields,
            before=before,
            created=action == FarmAuditEvent.Action.CREATED,
            deleted=action == FarmAuditEvent.Action.DELETED,
        ),
    )
