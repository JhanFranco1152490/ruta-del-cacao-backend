"""Finalizar una fermentación: el lote queda Fermentado y el cajón libre, en una sola transacción.
El cambio de estado del lote deja el evento del que el secado toma la hora mínima de su inicio."""

from django.db import transaction
from django.utils import timezone

from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import (
    FermentationNotInProgress,
    FermentationWithoutTurns,
    InvalidFermentation,
    StaleFermentationVersion,
)
from ..models import FermentationProcess, FermentationProcessAuditEvent
from .audit import record_process_event
from .queries import FERMENTED, FERMENTING, lock_process


@transaction.atomic
def finish_fermentation(actor, lot_id, expected_version: int, data: dict) -> FermentationProcess:
    """Cierra la fermentación con su hora de fin y sus observaciones. Necesita al menos un volteo,
    y el fin no puede ser anterior al último ni futuro. Si algo falla, nada cambia."""
    process = lock_process(actor, lot_id)
    if process.ended_at is not None:
        raise FermentationNotInProgress()
    check_expected_version(
        process, expected_version, stale=lambda: StaleFermentationVersion(process.pk)
    )
    last = process.turns.order_by("-turned_at").first()
    if last is None:
        raise FermentationWithoutTurns()
    ended_at = data["ended_at"]
    _check_end(process, last, ended_at)
    before = {"ended_at": None, "end_notes": process.end_notes}
    process.ended_at = ended_at
    process.end_notes = data.get("notes", "")
    process.finished_by = actor
    save_next_version(process, ["ended_at", "end_notes", "finished_by"])
    process.facility.release(process.lot, actor=actor)
    process.lot.advance_status(FERMENTING, FERMENTED, actor=actor)
    record_process_event(
        process=process,
        actor=actor,
        action=FermentationProcessAuditEvent.Action.FINISHED,
        before=before,
        after={"ended_at": process.ended_at, "end_notes": process.end_notes},
    )
    return process


def _check_end(process, last_turn, ended_at) -> None:
    if ended_at > timezone.now():
        raise InvalidFermentation("ended_at", "No puede ser una fecha futura.")
    # El fin puede caer en el mismo minuto del último volteo: se voltea y se saca el cacao.
    if ended_at < last_turn.turned_at:
        local = timezone.localtime(last_turn.turned_at)
        raise InvalidFermentation(
            "ended_at", f"No puede ser anterior al último volteo ({local:%d/%m/%Y %H:%M})."
        )
    if ended_at <= process.started_at:
        raise InvalidFermentation("ended_at", "Debe ser posterior al inicio de la fermentación.")
