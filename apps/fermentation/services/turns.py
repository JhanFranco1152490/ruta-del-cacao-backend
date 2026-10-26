"""Registrar, corregir y eliminar los volteos de una fermentación en curso.

Registrar llega desde la cola del dispositivo, también sin conexión: el `id` lo genera el
dispositivo, y reenviar el mismo volteo devuelve el que ya existe. Corregir y eliminar se hacen en
línea. Registrar y corregir evalúan los desvíos con el volteo ya guardado; corregir además retira
los avisos de los desvíos que ya no cumple.
"""

from django.db import transaction
from django.utils import timezone

from apps.common.audit import field_changes
from apps.common.contracts.alerts import notify, withdraw
from apps.common.db import save_translating_unique
from apps.common.versioning import check_expected_version, save_next_version

from ..alerts import stale_deviation_kinds, turn_alerts
from ..exceptions import (
    DuplicateTurnTime,
    FermentationNotInProgress,
    InvalidFermentation,
    StaleTurnVersion,
    TurnIdConflict,
    TurnNotFound,
)
from ..models import FermentationProcessAuditEvent, FermentationTurn
from .queries import lock_process

TIME_CONSTRAINT = "fermentation_turn_process_time_unique"
CONTENT_FIELDS = ("turned_at", "temperature_c", "ph", "notes")


@transaction.atomic
def record_turn(actor, lot_id, data: dict) -> tuple[FermentationTurn, bool]:
    """Guarda un volteo. Devuelve `(volteo, creado)`: un reenvío con los mismos datos devuelve el
    que ya existe (`creado=False`), para que reintentar un envío cortado nunca duplique."""
    process = lock_process(actor, lot_id)
    sent = _content(data)
    if (existing := _existing(data["id"])) is not None:
        return _resent(existing, process, sent), False
    _check_in_progress(process)
    _check_time(process, sent["turned_at"])
    turn = FermentationTurn(
        id=data["id"],
        process=process,
        recorded_by=actor,
        captured_at=data.get("captured_at"),
        **sent,
    )
    # El mismo `id` en otra fermentación no pasa por el mismo bloqueo: el choque llega como clave
    # primaria repetida, o como la misma hora si dos teléfonos mandan el mismo volteo.
    existing = save_translating_unique(
        lambda: turn.save(force_insert=True),
        constraint=TIME_CONSTRAINT,
        duplicate=lambda: _duplicate_time(process, sent["turned_at"]),
        find_existing=lambda: _existing(turn.pk),
    )
    if existing is not None:
        return _resent(existing, process, sent), False
    _record(turn, actor, FermentationProcessAuditEvent.Action.TURN_CREATED, {}, turn_values(turn))
    notify(turn_alerts(turn))
    return turn, True


@transaction.atomic
def update_turn(actor, lot_id, turn_id, expected_version: int, changes: dict) -> FermentationTurn:
    """Corrige un volteo mientras la fermentación sigue en curso. Cambiar la hora puede cambiar su
    número y el de los demás. Sin cambios reales, la versión no sube y no queda evento."""
    process = lock_process(actor, lot_id)
    _check_in_progress(process)
    turn = _turn_of(process, turn_id)
    check_expected_version(turn, expected_version, stale=lambda: StaleTurnVersion(turn))
    before = turn_values(turn)
    content = _content({**{field: getattr(turn, field) for field in CONTENT_FIELDS}, **changes})
    if "turned_at" in changes:
        _check_time(process, content["turned_at"])
    for field, value in content.items():
        setattr(turn, field, value)
    after = turn_values(turn)
    changed = [field for field in CONTENT_FIELDS if after[field] != before[field]]
    if not changed:
        return turn
    save_next_version(
        turn,
        changed,
        constraint=TIME_CONSTRAINT,
        duplicate=lambda: _duplicate_time(process, turn.turned_at),
    )
    _record(turn, actor, FermentationProcessAuditEvent.Action.TURN_UPDATED, before, after)
    # Un dato mal tecleado que se corrige no deja una alarma falsa: lo que ya no cumple se retira.
    if stale := stale_deviation_kinds(turn):
        withdraw(stale, fermentation_turn_id=turn.pk)
    notify(turn_alerts(turn))
    return turn


@transaction.atomic
def delete_turn(actor, lot_id, turn_id, expected_version: int) -> None:
    """Elimina un volteo registrado por error. El historial guarda una copia de lo que medía."""
    process = lock_process(actor, lot_id)
    _check_in_progress(process)
    turn = _turn_of(process, turn_id)
    check_expected_version(turn, expected_version, stale=lambda: StaleTurnVersion(turn))
    _record(turn, actor, FermentationProcessAuditEvent.Action.TURN_DELETED, turn_values(turn), {})
    turn.delete()


def turn_values(turn: FermentationTurn) -> dict:
    """Lo que mide un volteo, con los textos que entrega la API (temperatura con un decimal y pH
    con dos)."""
    return {
        "turned_at": turn.turned_at,
        "temperature_c": f"{turn.temperature_c:.1f}",
        "ph": f"{turn.ph:.2f}",
        "notes": turn.notes,
    }


def turn_number(turn: FermentationTurn) -> int:
    """La posición del volteo por hora entre los de su fermentación."""
    return FermentationTurn.objects.filter(
        process_id=turn.process_id, turned_at__lte=turn.turned_at
    ).count()


def _content(data: dict) -> dict:
    # Dos registros del mismo minuto son el mismo volteo: los segundos no se guardan.
    return {
        "turned_at": data["turned_at"].replace(second=0, microsecond=0),
        "temperature_c": data["temperature_c"],
        "ph": data["ph"],
        "notes": data.get("notes", ""),
    }


def _check_in_progress(process) -> None:
    if process.ended_at is not None:
        raise FermentationNotInProgress()


def _check_time(process, turned_at) -> None:
    if turned_at < process.started_at.replace(second=0, microsecond=0):
        raise InvalidFermentation(
            "turned_at", "No puede ser anterior al inicio de la fermentación."
        )
    if turned_at > timezone.now():
        raise InvalidFermentation("turned_at", "No puede ser una fecha futura.")


def _existing(turn_id) -> FermentationTurn | None:
    return FermentationTurn.objects.filter(pk=turn_id).first()


def _resent(existing: FermentationTurn, process, sent: dict) -> FermentationTurn:
    stored = {field: getattr(existing, field) for field in CONTENT_FIELDS}
    if existing.process_id != process.pk or stored != sent:
        raise TurnIdConflict()
    return existing


def _turn_of(process, turn_id) -> FermentationTurn:
    turn = process.turns.select_related("recorded_by").filter(pk=turn_id).first()
    if turn is None:
        raise TurnNotFound()
    return turn


def _duplicate_time(process, turned_at) -> DuplicateTurnTime:
    other = process.turns.filter(turned_at=turned_at).first()
    if other is None:
        return DuplicateTurnTime()
    return DuplicateTurnTime(other.pk, turn_number(other))


def _record(turn, actor, action: str, before: dict, after: dict) -> None:
    changes = field_changes(before, after)
    FermentationProcessAuditEvent.record(
        process_id=turn.process_id,
        turn_ref=turn.pk,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=turn.version,
        changes=changes,
    )
