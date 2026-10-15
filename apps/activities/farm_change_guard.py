from datetime import timedelta

from apps.common.farm_change_guards import PendingWork

from .choices import ActivityStatus
from .models import AgriculturalActivity
from .state import OVERDUE_AFTER_DAYS, today_in_bogota


def pending_activities(account, farm_id) -> PendingWork:
    """Las actividades sin realizar de `account` en parcelas de la finca `farm_id`.

    Las programadas y las retrasadas impiden cambiarla de finca: todavía se pueden reasignar, y
    hay que hacerlo (o registrarlas) antes, para que ninguna quede a nombre de alguien que ya no
    trabaja ahí. Las vencidas no: ya no se reasignan, solo se registran, así que bloquear por
    ellas dejaría a la persona atada a la finca por una labor que nunca se hizo. Se quedan a su
    nombre como constancia de que no se cumplió.
    """
    unfinished = AgriculturalActivity.objects.filter(
        assignee=account, plot__farm_id=farm_id
    ).exclude(status=ActivityStatus.DONE)
    # Vencida desde el día OVERDUE_AFTER_DAYS de atraso (ver `state.py`).
    first_overdue = today_in_bogota() - timedelta(days=OVERDUE_AFTER_DAYS)
    return PendingWork(
        blocking=unfinished.filter(scheduled_date__gt=first_overdue).count(),
        kept=unfinished.filter(scheduled_date__lte=first_overdue).count(),
    )
