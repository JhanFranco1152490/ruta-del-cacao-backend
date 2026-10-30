"""Los avisos de las actividades sin realizar: próxima, retrasada y vencida.

La evaluación periódica llama a `evaluate` con la fecha de hoy. Cada condición se repite un día
por cada día que dura (la próxima los dos días antes y el día mismo; la retrasada sus dos días),
y la clave lleva ese día: el aviso de hoy es otro que el de ayer y lo reemplaza. La vencida avisa
una sola vez, por vieja que sea.
"""

from datetime import timedelta

from apps.common.contracts.alerts import NotificationDraft
from apps.common.contracts.schedulers import Schedulers

from .choices import ActivityStatus
from .models import AgriculturalActivity
from .state import ActivityState, activity_state

# Desde cuántos días antes se recuerda una actividad programada.
UPCOMING_DAYS = 2


def evaluate(today, now=None):
    # Las actividades se miden en días: la hora no cambia nada.
    activities = list(
        AgriculturalActivity.objects.filter(
            status=ActivityStatus.SCHEDULED,
            scheduled_date__lte=today + timedelta(days=UPCOMING_DAYS),
        ).select_related("plot__farm", "assignee")
    )
    late = [a for a in activities if a.scheduled_date < today]
    schedulers = Schedulers({a.plot.farm.producer_id for a in late})

    for activity in activities:
        state, days_late = activity_state(activity, today)
        if state == ActivityState.SCHEDULED:
            if activity.assignee.is_active:
                days_before = (activity.scheduled_date - today).days
                yield _draft(activity, activity.assignee_id, "activity_upcoming", days_before)
            continue
        kind, day = (
            ("activity_overdue", None)
            if state == ActivityState.OVERDUE
            else ("activity_delayed", days_late)
        )
        for recipient_id in _late_recipients(activity, schedulers):
            yield _draft(activity, recipient_id, kind, day)


def _draft(activity, recipient_id, kind, day):
    key = f"{activity.pk}:{activity.scheduled_date}"
    return NotificationDraft(
        recipient_id=recipient_id,
        kind=kind,
        condition_key=key if day is None else f"{key}:{day}",
        thread_key=f"activity:{activity.pk}",
        activity_id=activity.pk,
        condition_date=activity.scheduled_date,
    )


def _late_recipients(activity, schedulers) -> set:
    """El responsable y quienes pueden programar en la finca de la actividad: son los que pueden
    registrarla tarde o moverla. Un conjunto, para que nadie reciba dos veces lo mismo."""
    recipients = schedulers.on_farm(activity.plot.farm.producer_id, activity.plot.farm_id)
    if activity.assignee.is_active:
        recipients.add(activity.assignee_id)
    return recipients
