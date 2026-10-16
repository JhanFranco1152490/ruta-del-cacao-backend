from functools import reduce
from operator import or_

from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import Notification


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
        )
        for draft in drafts
    ]
    if not rows:
        return 0

    with transaction.atomic():
        Notification.objects.bulk_create(rows, ignore_conflicts=True)
        # Con los conflictos ignorados, las filas que ya existían conservan su id: las que tienen
        # el id generado aquí son las nuevas.
        created = set(
            Notification.objects.filter(pk__in=[row.pk for row in rows]).values_list(
                "pk", flat=True
            )
        )
        new_rows = [row for row in rows if row.pk in created]
        _hide_previous(new_rows)
    return len(new_rows)


def _hide_previous(new_rows) -> None:
    if not new_rows:
        return
    threads = {(row.recipient_id, row.thread_key) for row in new_rows}
    same_thread = reduce(
        or_, (Q(recipient_id=recipient, thread_key=thread) for recipient, thread in threads)
    )
    now = timezone.now()
    (
        Notification.objects.filter(same_thread, dismissed_at__isnull=True)
        .exclude(pk__in=[row.pk for row in new_rows])
        .update(read_at=Coalesce("read_at", now), dismissed_at=now)
    )
