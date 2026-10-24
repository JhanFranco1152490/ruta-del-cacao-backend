from apps.common.audit import field_changes

from ..models import FermentationProcess, FermentationProcessAuditEvent

# Lo que describe el inicio de una fermentación, con los valores que entrega la API. Las cuentas y
# el cajón van por su id.
START_FIELDS = ("facility_id", "started_at", "responsible_id", "over_capacity")


def start_values(process: FermentationProcess) -> dict:
    return {field: getattr(process, field) for field in START_FIELDS}


def record_process_event(
    *, process: FermentationProcess, actor, action: str, before: dict, after: dict
) -> FermentationProcessAuditEvent:
    changes = field_changes(before, after)
    return FermentationProcessAuditEvent.record(
        process=process,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=process.version,
        changes=changes,
    )
