"""El estado que se muestra de una actividad: sale de lo guardado y de la fecha de hoy.

Retrasada y vencida no se guardan. Una actividad cuya fecha pasó se ve retrasada desde el día
siguiente, y todavía se puede reprogramar; al cumplir los días de tolerancia sin reprogramarse ni
registrarse queda vencida: ya no se reprograma ni se elimina, pero si la labor se hizo tarde se
puede registrar.
"""

from datetime import date, datetime

from django.db import models
from django.utils import timezone

from .choices import ActivityStatus

# El frontend tiene la misma constante: si cambia aquí, cambia allá.
OVERDUE_AFTER_DAYS = 3


class ActivityState(models.TextChoices):
    SCHEDULED = "scheduled", "Programada"
    DELAYED = "delayed", "Retrasada"
    OVERDUE = "overdue", "Vencida"
    DONE = "done", "Realizada"


def today_in_bogota(now: datetime | None = None) -> date:
    # La zona del proyecto es America/Bogota: la medianoche que cuenta es la de allá, no la UTC.
    return timezone.localdate(now)


def activity_state(activity, today: date) -> tuple[ActivityState, int]:
    """El estado y los días de retraso. Una realizada no tiene retraso, aunque su fecha sea
    vieja."""
    if activity.status == ActivityStatus.DONE:
        return ActivityState.DONE, 0
    days_late = (today - activity.scheduled_date).days
    if days_late <= 0:
        return ActivityState.SCHEDULED, 0
    if days_late < OVERDUE_AFTER_DAYS:
        return ActivityState.DELAYED, days_late
    return ActivityState.OVERDUE, days_late


def can_edit(state: ActivityState) -> bool:
    return state in (ActivityState.SCHEDULED, ActivityState.DELAYED)


def can_delete(state: ActivityState) -> bool:
    return state in (ActivityState.SCHEDULED, ActivityState.DELAYED)


def can_complete(state: ActivityState) -> bool:
    return state != ActivityState.DONE
