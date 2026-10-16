from apps.common.audit import field_changes

from ..models import Harvest, HarvestAuditEvent

# Lo que describe a la cosecha, con los valores que entrega la API.
VALUE_FIELDS = (
    "harvest_date",
    "green_weight_kg",
    "variety_id",
    "collector_id",
    "characterization_version",
)


def harvest_values(harvest: Harvest) -> dict:
    return {field: getattr(harvest, field) for field in VALUE_FIELDS}


def record_harvest_event(
    *, harvest: Harvest, actor, action: str, before: dict, after: dict
) -> HarvestAuditEvent:
    changes = field_changes(before, after, decimal_places=1)
    return HarvestAuditEvent.record(
        harvest=harvest if action != HarvestAuditEvent.Action.DELETED else None,
        harvest_ref=harvest.pk,
        plot_ref=harvest.plot_id,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=harvest.version,
        changes=changes,
    )
