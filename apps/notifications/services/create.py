from functools import reduce
from operator import or_

from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..choices import NotificationSeverity
from ..models import Notification
from ..push.background import run_in_background
from ..push.send import send_pending_pushes

# Cuántos avisos o hilos entran en una sentencia: la primera evaluación, o la que sigue a una
# caída larga, puede traer miles, y una sola sentencia con todos sería enorme.
CHUNK_SIZE = 500


def create_notifications(drafts) -> int:
    """Guarda los avisos que todavía no existen y dice cuántos son nuevos.

    Uno que ya existe (la misma persona, el mismo tipo y la misma condición) se ignora: la
    restricción única lo decide, también si dos evaluaciones corren a la vez. Cada aviso nuevo
    oculta los anteriores de la misma persona sobre lo mismo (`thread_key`), que quedan leídos y
    eliminados: así el recordatorio de hoy reemplaza al de ayer y la vencida a la retrasada. Uno
    que se refiere a un momento anterior al de uno que ya está en la bandeja (un registro viejo que
    llega tarde de la cola, o que se corrige) nace oculto: no le quita el lugar al más reciente.
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
    horario de push. Los demás salen en la evaluación de cada hora.

    Sale fuera de la petición y cuando se confirma la transacción en curso, si la hay: el hilo usa
    su propia conexión y no vería avisos sin confirmar. Si la push no sale, el aviso sigue en la
    bandeja y la evaluación siguiente vuelve a intentar."""
    critical = [row.pk for row in new_rows if row.severity == NotificationSeverity.CRITICAL]
    if not critical:
        return
    now = timezone.now()
    transaction.on_commit(
        lambda: run_in_background(
            send_pending_pushes,
            now,
            notification_ids=critical,
            where="la push de un aviso crítico",
        )
    )


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
    """Oculta los avisos que los nuevos reemplazan y los nuevos que llegaron tarde.

    Reemplazar es por la hora a la que se refiere el aviso (`condition_at`): uno nuevo reemplaza a
    los que ya están en su hilo si no es anterior a ellos. Los avisos sin hora (los de actividades)
    siempre reemplazan a los anteriores."""
    if not new_rows:
        return
    new_ids = {row.pk for row in new_rows}
    new_by_thread: dict = {}
    for row in new_rows:
        new_by_thread.setdefault((row.recipient_id, row.thread_key), []).append(row)
    now = timezone.now()
    late_ids: list = []
    for chunk in _chunks(sorted(new_by_thread)):
        existing = _visible_in_threads(chunk, exclude=new_ids)
        replaced_ids: list = []
        for thread in chunk:
            replaced, late = _split_thread(new_by_thread[thread], existing.get(thread, []))
            replaced_ids.extend(replaced)
            late_ids.extend(late)
        _hide(replaced_ids, now)
    for chunk in _chunks(late_ids):
        _hide(chunk, now)


def _visible_in_threads(threads, *, exclude) -> dict:
    """Los avisos que siguen en la bandeja de cada hilo, como `(id, condition_at)`."""
    same_thread = reduce(
        or_, (Q(recipient_id=recipient, thread_key=thread) for recipient, thread in threads)
    )
    visible = (
        Notification.objects.filter(same_thread, dismissed_at__isnull=True)
        .exclude(pk__in=exclude)
        .values_list("pk", "recipient_id", "thread_key", "condition_at")
    )
    by_thread: dict = {}
    for pk, recipient_id, thread_key, condition_at in visible:
        by_thread.setdefault((recipient_id, thread_key), []).append((pk, condition_at))
    return by_thread


def _split_thread(new_rows, existing) -> tuple[list, list]:
    """De un hilo: los ids de los que ya estaban y los nuevos reemplazan, y los de los nuevos que
    llegaron tarde."""
    late = [
        row
        for row in new_rows
        if any(_is_before(row.condition_at, condition_at) for _, condition_at in existing)
    ]
    on_time = [row for row in new_rows if row not in late]
    replaced = [
        pk
        for pk, condition_at in existing
        if any(not _is_before(row.condition_at, condition_at) for row in on_time)
    ]
    return replaced, [row.pk for row in late]


def _is_before(moment, other) -> bool:
    """Si `moment` es anterior a `other`. Sin hora no hay con qué comparar: no lo es."""
    return moment is not None and other is not None and moment < other


def _hide(ids: list, now) -> None:
    if ids:
        Notification.objects.filter(pk__in=ids).update(
            read_at=Coalesce("read_at", now), dismissed_at=now
        )
