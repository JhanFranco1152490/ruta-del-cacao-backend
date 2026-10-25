"""Corregir el inicio de un secado mientras no tenga bitácora: la marquesina, la hora, la humedad
de entrada y el responsable."""

from django.db import transaction

from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import DryingHasLogs, DryingNotInProgress, StaleDryingVersion
from ..models import DryingProcess, DryingProcessAuditEvent
from .audit import record_process_event, start_values
from .queries import SOLAR_DRYER, lock_process
from .start import check_entry_moisture, check_start_time, choose_responsible, find_dryer


@transaction.atomic
def correct_start(actor, lot_id, expected_version: int, changes: dict) -> DryingProcess:
    """Aplica los cambios al inicio. Cambiar de marquesina libera la anterior y ocupa la nueva en
    la misma transacción. Sin cambios reales, la versión no sube y no queda evento."""
    process = lock_process(actor, lot_id)
    lot = process.lot
    if process.ended_at is not None:
        raise DryingNotInProgress()
    check_expected_version(process, expected_version, stale=lambda: StaleDryingVersion(process.pk))
    if process.logs.exists():
        raise DryingHasLogs()
    before = start_values(process)
    if "started_at" in changes:
        check_start_time(lot, changes["started_at"])
        process.started_at = changes["started_at"]
    if "responsible_id" in changes:
        process.responsible = choose_responsible(actor, lot, changes["responsible_id"])
    if "facility_id" in changes and changes["facility_id"] != process.facility_id:
        dryer = find_dryer(lot, changes["facility_id"])
        process.facility.release(lot, actor=actor)
        dryer.occupy(lot, kind=SOLAR_DRYER, actor=actor)
        process.facility = dryer
    if "entry_moisture_pct" in changes:
        process.entry_moisture_out_of_range = check_entry_moisture(
            lot,
            changes["entry_moisture_pct"],
            confirmed=changes.get("confirm_entry_moisture", False),
        )
        process.entry_moisture_pct = changes["entry_moisture_pct"]
    after = start_values(process)
    changed = [field for field in after if after[field] != before[field]]
    if not changed:
        return process
    save_next_version(process, [field.removesuffix("_id") for field in changed])
    record_process_event(
        process=process,
        actor=actor,
        action=DryingProcessAuditEvent.Action.UPDATED,
        before=before,
        after=after,
    )
    return process
