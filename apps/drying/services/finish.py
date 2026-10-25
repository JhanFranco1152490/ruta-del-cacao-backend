"""Finalizar un secado: el resultado con su rendimiento, el lote Seco y la marquesina libre."""

from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import (
    DryingNotInProgress,
    DryingWithoutLogs,
    DryWeightAboveGreen,
    InvalidDrying,
    StaleDryingVersion,
)
from ..models import RESULT_FIELDS, DryingProcess, DryingProcessAuditEvent
from ..rules import compute_yield
from .audit import record_process_event
from .queries import DRIED, DRYING, lock_process


@transaction.atomic
def finish_drying(actor, lot_id, expected_version: int, data: dict) -> DryingProcess:
    """Guarda el resultado, deja el lote Seco y libera la marquesina, en una sola transacción: si
    algo falla, el secado sigue en curso y la marquesina ocupada."""
    process = lock_process(actor, lot_id)
    if process.ended_at is not None:
        raise DryingNotInProgress()
    check_expected_version(process, expected_version, stale=lambda: StaleDryingVersion(process.pk))
    logs = process.logs.aggregate(last=Max("measured_at"), sun=Sum("sun_hours"))
    if logs["last"] is None:
        raise DryingWithoutLogs()
    _check_end(process, data["ended_at"], logs["last"])
    lot = process.lot
    green_weight_kg = lot.harvest.green_weight_kg
    if data["dry_weight_kg"] > green_weight_kg:
        raise DryWeightAboveGreen(green_weight_kg)
    before = _result_values(process)
    process.ended_at = data["ended_at"]
    process.final_moisture_pct = data["final_moisture_pct"]
    process.dry_weight_kg = data["dry_weight_kg"]
    process.yield_pct = compute_yield(data["dry_weight_kg"], green_weight_kg)
    process.total_sun_hours = logs["sun"]
    process.finished_by = actor
    save_next_version(process, [*RESULT_FIELDS, "finished_by"])
    process.facility.release(lot, actor=actor)
    lot.advance_status(DRYING, DRIED, actor=actor)
    record_process_event(
        process=process,
        actor=actor,
        action=DryingProcessAuditEvent.Action.FINISHED,
        before=before,
        after=_result_values(process),
    )
    return process


def _check_end(process, ended_at, last_measured_at) -> None:
    if ended_at > timezone.now():
        raise InvalidDrying("ended_at", "No puede ser una fecha futura.")
    if ended_at < last_measured_at or ended_at <= process.started_at:
        raise InvalidDrying(
            "ended_at",
            "No puede ser anterior a la última medición "
            f"({timezone.localtime(last_measured_at):%d/%m/%Y %H:%M}).",
        )


def _result_values(process) -> dict:
    return {field: getattr(process, field) for field in RESULT_FIELDS}
