from apps.common.audit import field_changes

from ..models import ONE_DECIMAL, DryingProcess, DryingProcessAuditEvent

# Lo que describe el inicio de un secado, con los valores que entrega la API. Las cuentas y la
# marquesina van por su id.
START_FIELDS = (
    "facility_id",
    "started_at",
    "entry_moisture_pct",
    "entry_moisture_out_of_range",
    "responsible_id",
)


def start_values(process: DryingProcess) -> dict:
    return {field: getattr(process, field) for field in START_FIELDS}


def record_process_event(
    *,
    process: DryingProcess,
    actor,
    action: str,
    before: dict,
    after: dict,
    version: int | None = None,
    log_ref=None,
) -> DryingProcessAuditEvent:
    changes = field_changes(before, after, decimal_places=ONE_DECIMAL)
    return DryingProcessAuditEvent.record(
        process=process,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=process.version if version is None else version,
        log_ref=log_ref,
        changes=changes,
    )
