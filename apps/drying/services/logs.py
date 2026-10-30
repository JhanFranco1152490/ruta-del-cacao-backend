"""Registrar, corregir y eliminar la bitácora de un secado en curso.

Registrar llega desde la cola del dispositivo, también sin conexión: el `id` lo genera el
dispositivo, y reenviar la misma bitácora devuelve la que ya existe. Corregir y eliminar se hacen
en línea. Registrar y corregir evalúan los desvíos con la bitácora ya guardada; corregir además
retira los avisos de los desvíos que ya no cumple.
"""

from django.db import transaction
from django.utils import timezone

from apps.common.contracts.alerts import notify, resolve, withdraw
from apps.common.db import save_translating_unique
from apps.common.versioning import check_expected_version, save_next_version

from ..alerts import LOG_DUE, drying_log_alerts, stale_deviation_kinds
from ..exceptions import (
    DryingHoursExceeded,
    DryingLogIdConflict,
    DryingLogNotFound,
    DryingNotInProgress,
    DuplicateDryingLogDate,
    InvalidDrying,
    StaleDryingLogVersion,
)
from ..models import LOG_DATE_UNIQUE_CONSTRAINT, DryingLogEntry, DryingProcessAuditEvent
from ..rules import available_hours, day_number
from .audit import record_process_event
from .queries import lock_process

CONTENT_FIELDS = (
    "measured_at",
    "moisture_pct",
    "sun_hours",
    "shade_hours",
    "turn_count",
    "turn_frequency_hours",
    "weather",
    "notes",
)
NOTES_DEFAULT = ""


@transaction.atomic
def record_log(actor, lot_id, data: dict) -> tuple[DryingLogEntry, bool]:
    """Guarda la bitácora de un día. Devuelve `(bitácora, creada)`: un reenvío con los mismos datos
    devuelve la que ya existe (`creada=False`), para que reintentar un envío cortado nunca
    duplique."""
    process = lock_process(actor, lot_id)
    sent = _content(data)
    if (existing := _existing(data["id"])) is not None:
        return _resent(existing, process, sent), False
    _check_in_progress(process)
    entry = DryingLogEntry(
        id=data["id"],
        process=process,
        recorded_by=actor,
        captured_at=data.get("captured_at"),
        **sent,
    )
    _check_content(process, entry)
    # El mismo `id` en otro secado no pasa por el mismo bloqueo: el choque llega como clave
    # primaria repetida, o como la misma fecha si dos teléfonos mandan la misma bitácora.
    existing = save_translating_unique(
        lambda: entry.save(force_insert=True),
        constraint=LOG_DATE_UNIQUE_CONSTRAINT,
        duplicate=lambda: _duplicate_date(process, entry.log_date),
        find_existing=lambda: _existing(entry.pk),
    )
    if existing is not None:
        return _resent(existing, process, sent), False
    _record(entry, actor, DryingProcessAuditEvent.Action.LOG_CREATED, {}, log_values(entry))
    # Llegó una bitácora: la que estaba pendiente deja de pedir atención.
    resolve(process.lot_id, [LOG_DUE])
    notify(drying_log_alerts(entry))
    return entry, True


@transaction.atomic
def update_log(actor, lot_id, log_id, expected_version: int, changes: dict) -> DryingLogEntry:
    """Corrige una bitácora mientras el secado sigue en curso. Cambiar la hora de la medición puede
    cambiar su fecha y su día. Sin cambios reales, la versión no sube, no queda evento y no se
    vuelve a evaluar."""
    process = lock_process(actor, lot_id)
    _check_in_progress(process)
    entry = _entry_of(process, log_id)
    check_expected_version(entry, expected_version, stale=lambda: StaleDryingLogVersion(entry))
    before = log_values(entry)
    current = {field: getattr(entry, field) for field in CONTENT_FIELDS}
    for field, value in _content({**current, **changes}).items():
        setattr(entry, field, value)
    _check_content(process, entry)
    after = log_values(entry)
    changed = [field for field in after if after[field] != before[field]]
    if not changed:
        return entry
    save_next_version(
        entry,
        [*changed, "log_date", "day_number"],
        constraint=LOG_DATE_UNIQUE_CONSTRAINT,
        duplicate=lambda: _duplicate_date(process, entry.log_date, other_than=entry.pk),
    )
    _record(entry, actor, DryingProcessAuditEvent.Action.LOG_UPDATED, before, after)
    # Un dato mal tecleado que se corrige no deja una alarma falsa: lo que ya no cumple se retira.
    if stale := stale_deviation_kinds(entry):
        withdraw(stale, drying_log_id=entry.pk)
    notify(drying_log_alerts(entry))
    return entry


@transaction.atomic
def delete_log(actor, lot_id, log_id, expected_version: int) -> None:
    """Elimina una bitácora registrada por error. El historial guarda una copia de lo que medía."""
    process = lock_process(actor, lot_id)
    _check_in_progress(process)
    entry = _entry_of(process, log_id)
    check_expected_version(entry, expected_version, stale=lambda: StaleDryingLogVersion(entry))
    _record(entry, actor, DryingProcessAuditEvent.Action.LOG_DELETED, log_values(entry), {})
    entry.delete()


def log_values(entry: DryingLogEntry) -> dict:
    """Lo que dice una bitácora, con los valores que entrega la API."""
    return {field: getattr(entry, field) for field in CONTENT_FIELDS}


def _content(data: dict) -> dict:
    content = {field: data.get(field) for field in CONTENT_FIELDS}
    # Dos mediciones del mismo minuto son la misma: los segundos no se guardan.
    content["measured_at"] = content["measured_at"].replace(second=0, microsecond=0)
    content["notes"] = content["notes"] or NOTES_DEFAULT
    return content


def _check_in_progress(process) -> None:
    if process.ended_at is not None:
        raise DryingNotInProgress()


def _check_content(process, entry) -> None:
    """Las reglas que dependen del secado o de varios campos a la vez: la hora de la medición, los
    volteos con su frecuencia y las horas del día. Deja calculados la fecha y el día."""
    if entry.measured_at < process.started_at.replace(second=0, microsecond=0):
        raise InvalidDrying("measured_at", "No puede ser anterior al inicio del secado.")
    now = timezone.now()
    if entry.measured_at > now:
        raise InvalidDrying("measured_at", "No puede ser una fecha futura.")
    if entry.turn_count > 0 and entry.turn_frequency_hours is None:
        raise InvalidDrying("turn_frequency_hours", "Indica cada cuántas horas se volteó.")
    if entry.turn_count == 0 and entry.turn_frequency_hours is not None:
        raise InvalidDrying("turn_frequency_hours", "Sin volteos no hay frecuencia.")
    entry.log_date = timezone.localdate(entry.measured_at)
    entry.day_number = day_number(entry.log_date, process.started_at)
    hours = available_hours(entry.log_date, process.started_at, now)
    if entry.sun_hours + (entry.shade_hours or 0) > hours:
        first_day = entry.log_date == timezone.localdate(process.started_at)
        raise DryingHoursExceeded(
            hours, timezone.localtime(process.started_at) if first_day else None
        )


def _existing(log_id) -> DryingLogEntry | None:
    return DryingLogEntry.objects.filter(pk=log_id).first()


def _resent(existing: DryingLogEntry, process, sent: dict) -> DryingLogEntry:
    stored = {field: getattr(existing, field) for field in CONTENT_FIELDS}
    if existing.process_id != process.pk or stored != sent:
        raise DryingLogIdConflict()
    return existing


def _entry_of(process, log_id) -> DryingLogEntry:
    entry = process.logs.select_related("recorded_by").filter(pk=log_id).first()
    if entry is None:
        raise DryingLogNotFound()
    return entry


def _duplicate_date(process, log_date, other_than=None) -> DuplicateDryingLogDate:
    other = process.logs.filter(log_date=log_date).exclude(pk=other_than).first()
    if other is None:
        return DuplicateDryingLogDate()
    return DuplicateDryingLogDate(other.pk, other.day_number)


def _record(entry, actor, action: str, before: dict, after: dict) -> None:
    record_process_event(
        process=entry.process,
        actor=actor,
        action=action,
        before=before,
        after=after,
        version=entry.version,
        log_ref=entry.pk,
    )
