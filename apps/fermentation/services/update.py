"""Corregir el inicio de una fermentación mientras no tenga volteos: el cajón, la hora y el
responsable."""

from django.db import transaction

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import (
    FermentationHasTurns,
    FermentationNotFound,
    FermentationNotInProgress,
    StaleFermentationVersion,
)
from ..models import FermentationProcess, FermentationProcessAuditEvent
from .audit import record_process_event, start_values
from .queries import FERMENTATION_BOX, PROCESS_SCOPE
from .start import check_capacity, check_start_time, choose_responsible, find_box


@transaction.atomic
def correct_start(actor, lot_id, expected_version: int, changes: dict) -> FermentationProcess:
    """Aplica los cambios al inicio. Cambiar de cajón libera el anterior y ocupa el nuevo en la
    misma transacción. Sin cambios reales, la versión no sube y no queda evento."""
    process = lock_process(actor, lot_id)
    lot = process.lot
    if process.ended_at is not None:
        raise FermentationNotInProgress()
    check_expected_version(
        process, expected_version, stale=lambda: StaleFermentationVersion(process.pk)
    )
    if process.turns.exists():
        raise FermentationHasTurns()
    before = start_values(process)
    if "started_at" in changes:
        check_start_time(lot, changes["started_at"])
        process.started_at = changes["started_at"]
    if "responsible_id" in changes:
        process.responsible = choose_responsible(actor, lot, changes["responsible_id"])
    if "facility_id" in changes and changes["facility_id"] != process.facility_id:
        box = find_box(lot, changes["facility_id"])
        process.facility.release(lot, actor=actor)
        box.occupy(lot, kind=FERMENTATION_BOX, actor=actor)
        confirmed = changes.get("confirm_over_capacity", False)
        process.over_capacity = check_capacity(lot, box, confirmed=confirmed)
        process.facility = box
    after = start_values(process)
    changed = [field for field in after if after[field] != before[field]]
    if not changed:
        return process
    save_next_version(process, [field.removesuffix("_id") for field in changed])
    record_process_event(
        process=process,
        actor=actor,
        action=FermentationProcessAuditEvent.Action.UPDATED,
        before=before,
        after=after,
    )
    return process


def lock_process(actor, lot_id) -> FermentationProcess:
    """La fermentación, con la finca de su lote bloqueada hasta el final de la transacción."""
    lock_aggregate_root(
        FermentationProcess,
        lot_id,
        root="lot__harvest__plot__farm",
        scope=owner_filter(actor, PROCESS_SCOPE["field"], farm=PROCESS_SCOPE["farm"]),
        not_found=FermentationNotFound,
    )
    return FermentationProcess.objects.select_related(
        "lot__harvest__plot__farm", "facility__farm", "responsible"
    ).get(pk=lot_id)
