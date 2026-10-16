"""Los avisos de las actividades sin realizar: próxima, retrasada y vencida.

La evaluación periódica llama a `evaluate` con la fecha de hoy. Cada condición se repite un día
por cada día que dura (la próxima los dos días antes y el día mismo; la retrasada sus dos días),
y la clave lleva ese día: el aviso de hoy es otro que el de ayer y lo reemplaza. La vencida avisa
una sola vez, por vieja que sea.
"""

from datetime import timedelta

from django.contrib.auth.models import Permission
from django.db.models import Q

from apps.common.alerts import NotificationDraft
from apps.common.ownership import reaches_all_farms

from .choices import ActivityStatus
from .models import AgriculturalActivity
from .state import ActivityState, activity_state

User = AgriculturalActivity._meta.get_field("assignee").related_model

# Desde cuántos días antes se recuerda una actividad programada.
UPCOMING_DAYS = 2


def evaluate(today):
    activities = list(
        AgriculturalActivity.objects.filter(
            status=ActivityStatus.SCHEDULED,
            scheduled_date__lte=today + timedelta(days=UPCOMING_DAYS),
        ).select_related("plot__farm", "assignee")
    )
    late = [a for a in activities if a.scheduled_date < today]
    schedulers = _schedulers_by_producer({a.plot.farm.producer_id for a in late})

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
    recipients = {
        account.pk
        for account, farm_ids in schedulers.get(activity.plot.farm.producer_id, [])
        if farm_ids is None or activity.plot.farm_id in farm_ids
    }
    if activity.assignee.is_active:
        recipients.add(activity.assignee_id)
    return recipients


def _schedulers_by_producer(producer_ids) -> dict:
    """Las cuentas activas de esos productores que pueden programar, con las fincas que alcanzan
    (`None` si son todas). Una sola consulta para todas las actividades: el número de consultas
    crece con las cuentas, no con las actividades."""
    if not producer_ids:
        return {}
    permission = Permission.objects.filter(
        content_type__app_label="activities", codename="add_agriculturalactivity"
    )
    accounts = (
        User.objects.filter(
            Q(user_permissions__in=permission) | Q(groups__permissions__in=permission),
            producer_id__in=producer_ids,
            is_active=True,
            is_superuser=False,
        )
        .distinct()
        .prefetch_related("farms")
    )
    by_producer: dict = {}
    for account in accounts:
        farm_ids = None if reaches_all_farms(account) else {f.pk for f in account.farms.all()}
        by_producer.setdefault(account.producer_id, []).append((account, farm_ids))
    return by_producer
