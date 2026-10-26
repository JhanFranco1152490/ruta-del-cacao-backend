from functools import reduce
from operator import or_

from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.common.exceptions import log_unhandled_error

from ..choices import NotificationSeverity
from ..models import Notification
from ..push.send import send_pending_pushes

# Cuántos avisos o hilos entran en una sentencia: la primera evaluación, o la que sigue a una
# caída larga, puede traer miles, y una sola sentencia con todos sería enorme.
CHUNK_SIZE = 500


def create_notifications(drafts) -> int:
    """Guarda los avisos que todavía no existen y dice cuántos son nuevos.

    Uno que ya existe (la misma persona, el mismo tipo y la misma condición) se ignora: la
    restricción única lo decide, también si dos evaluaciones corren a la vez. Cada aviso nuevo
    oculta los anteriores de la misma persona sobre lo mismo (`thread_key`), que quedan leídos y
    eliminados: así el recordatorio de hoy reemplaza al de ayer y la vencida a la retrasada.
    """
    rows = [
        Notification(
            recipient_id=draft.recipient_id,
            kind=draft.kind,
            severity=draft.severity,
            condition_key=draft.condition_key,
            thread_key=draft.thread_key,
            activity_id=draft.activity_id,
            detection_id=draft.detection_id,
            condition_date=draft.condition_date,
            lot_id=draft.lot_id,
            fermentation_turn_id=draft.fermentation_turn_id,
            drying_log_id=draft.drying_log_id,
            condition_at=draft.condition_at,
        )
        for draft in drafts
    ]
    # Los que ya existen no se escriben: la evaluación horaria vuelve a calcular todo lo vencido
    # desde siempre, y esa lista solo crece.
    rows = _without_existing(rows)
    if not rows:
        return 0

    with transaction.atomic():
        Notification.objects.bulk_create(rows, ignore_conflicts=True)
        # Con los conflictos ignorados, las filas que ya existían conservan su id: las que tienen
        # el id generado aquí son las nuevas.
        created = set()
        for chunk in _chunks(rows):
            created.update(
                Notification.objects.filter(pk__in=[row.pk for row in chunk]).values_list(
                    "pk", flat=True
                )
            )
        new_rows = [row for row in rows if row.pk in created]
        _hide_previous(new_rows)
    _push_critical(new_rows)
    return len(new_rows)


def _push_critical(new_rows) -> None:
    """Un aviso crítico (el sobresecado) no espera a la evaluación siguiente: sale ya, si es
    horario de push. Los demás salen en la evaluación de cada hora."""
    critical = [row.pk for row in new_rows if row.severity == NotificationSeverity.CRITICAL]
    if not critical:
        return
    try:
        send_pending_pushes(timezone.now(), notification_ids=critical)
    except Exception as exc:
        # Una push que no sale no deshace el aviso: sigue en la bandeja, y la evaluación siguiente
        # vuelve a intentar.
        log_unhandled_error(exc, where="la push de un aviso crítico")


def _chunks(items: list):
    for start in range(0, len(items), CHUNK_SIZE):
        yield items[start : start + CHUNK_SIZE]


def _without_existing(rows: list[Notification]) -> list[Notification]:
    """Los avisos cuya persona, tipo y condición todavía no tienen fila."""
    existing: set = set()
    for chunk in _chunks(rows):
        existing.update(
            Notification.objects.filter(
                condition_key__in={row.condition_key for row in chunk},
                recipient_id__in={row.recipient_id for row in chunk},
            ).values_list("recipient_id", "kind", "condition_key")
        )
    return [row for row in rows if (row.recipient_id, row.kind, row.condition_key) not in existing]


def _hide_previous(new_rows) -> None:
    if not new_rows:
        return
    new_ids_by_thread: dict = {}
    for row in new_rows:
        new_ids_by_thread.setdefault((row.recipient_id, row.thread_key), []).append(row.pk)
    threads = sorted(new_ids_by_thread)
    now = timezone.now()
    for chunk in _chunks(threads):
        same_thread = reduce(
            or_, (Q(recipient_id=recipient, thread_key=thread) for recipient, thread in chunk)
        )
        (
            Notification.objects.filter(same_thread, dismissed_at__isnull=True)
            .exclude(pk__in=[pk for thread in chunk for pk in new_ids_by_thread[thread]])
            .update(read_at=Coalesce("read_at", now), dismissed_at=now)
        )
