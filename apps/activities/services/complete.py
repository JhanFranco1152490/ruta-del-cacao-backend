from django.db import transaction
from django.utils import timezone

from apps.common.versioning import save_next_version

from ..choices import ActivityStatus, ActivityType
from ..exceptions import ActivityAlreadyDone, InvalidActivity, MonitoringRequiresResult
from ..models import AgriculturalActivity, AgriculturalActivityAuditEvent
from ..state import today_in_bogota
from . import queries
from .audit import record_activity_event

COMPLETION_FIELDS = ["status", "done_date", "completed_by", "completed_at", "captured_at"]


@transaction.atomic
def complete_activity(actor, activity_id, data: dict) -> tuple[AgriculturalActivity, bool]:
    """Registra que la labor se hizo. Devuelve `(actividad, cambió)`.

    Llega desde la cola del dispositivo, a veces horas después: no pide versión, porque lo que
    importa es que la actividad siga sin realizar (si la reprogramaron entretanto, la labor igual
    se hizo). El mismo registro reenviado responde sin escribir nada.
    """
    if data.get("inputs"):
        raise InvalidActivity("inputs", "Todavía no se pueden registrar insumos en una actividad.")
    activity = queries.lock_activity(actor, activity_id)
    if activity.status == ActivityStatus.DONE:
        if activity.done_date == data["done_date"]:
            return activity, False
        raise ActivityAlreadyDone()
    if activity.activity_type == ActivityType.PHYTOSANITARY_MONITORING:
        raise MonitoringRequiresResult()
    _ensure_valid_date(activity, data["done_date"])

    activity.status = ActivityStatus.DONE
    activity.done_date = data["done_date"]
    activity.completed_by = actor
    activity.completed_at = timezone.now()
    activity.captured_at = data.get("captured_at")
    save_next_version(activity, COMPLETION_FIELDS)
    record_activity_event(
        activity=activity,
        actor=actor,
        action=AgriculturalActivityAuditEvent.Action.COMPLETED,
        before={"status": ActivityStatus.SCHEDULED, "done_date": None},
        after={"status": activity.status, "done_date": activity.done_date},
    )
    return activity, True


def _ensure_valid_date(activity: AgriculturalActivity, done_date) -> None:
    if done_date > today_in_bogota():
        raise InvalidActivity("done_date", "La fecha no puede ser futura.")
    # Una labor se puede adelantar a la fecha programada, pero no ser anterior a su planeación.
    planned_on = timezone.localdate(activity.created_at)
    if done_date < planned_on:
        raise InvalidActivity(
            "done_date",
            "La fecha no puede ser anterior a la programación de la actividad "
            f"({planned_on.strftime('%d/%m/%Y')}).",
        )
