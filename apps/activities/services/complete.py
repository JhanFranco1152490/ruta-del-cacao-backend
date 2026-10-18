from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.common.versioning import save_next_version

from ..choices import ActivityStatus, ActivityType
from ..exceptions import ActivityAlreadyDone, InvalidActivity, MonitoringRequiresResult
from ..models import AgriculturalActivity, AgriculturalActivityAuditEvent
from ..state import today_in_bogota
from . import queries
from .audit import record_activity_event
from .consumption import (
    discount_inputs,
    inputs_for_history,
    locked_inputs,
    sent_inputs,
    used_inputs,
)

COMPLETION_FIELDS = ["status", "done_date", "completed_by", "completed_at", "captured_at"]


@transaction.atomic
def complete_activity(actor, activity_id, data: dict) -> tuple[AgriculturalActivity, bool]:
    """Registra que la labor se hizo, con los insumos que gastó. Devuelve `(actividad, cambió)`.

    Llega desde la cola del dispositivo, a veces horas después: no pide versión, porque lo que
    importa es que la actividad siga sin realizar (si la reprogramaron entretanto, la labor igual
    se hizo). El mismo registro reenviado responde sin escribir nada ni volver a descontar.
    """
    sent = sent_inputs(data.get("inputs") or [])
    activity = queries.lock_activity(actor, activity_id)
    queries.ensure_can_complete(actor, activity)
    if activity.status == ActivityStatus.DONE:
        if activity.done_date == data["done_date"] and used_inputs(activity) == sent:
            return activity, False
        raise ActivityAlreadyDone()
    if activity.activity_type == ActivityType.PHYTOSANITARY_MONITORING:
        raise MonitoringRequiresResult()
    if sent and activity.activity_type == ActivityType.INVENTORY:
        # El conteo se registra en el inventario: descontar aquí lo contaría dos veces.
        raise InvalidActivity("inputs", "Una actividad de inventario no registra insumos.")
    ensure_valid_done_date(data["done_date"], not_before=timezone.localdate(activity.created_at))
    items = locked_inputs(activity.plot.farm.producer_id, sent)

    mark_done(activity, actor, data["done_date"], data.get("captured_at"))
    discount_inputs(activity, items, sent, actor)
    record_completion(activity, actor, sent)
    return activity, True


def ensure_valid_done_date(done_date: date, *, not_before: date) -> None:
    """La fecha de realización no es futura ni anterior a `not_before`: la programación de la
    actividad, o el monitoreo que atiende un control. Una labor se puede adelantar a la fecha
    programada, pero no ser anterior a su planeación."""
    if done_date > today_in_bogota():
        raise InvalidActivity("done_date", "La fecha no puede ser futura.")
    if done_date < not_before:
        raise InvalidActivity(
            "done_date",
            "La fecha no puede ser anterior a la programación de la actividad "
            f"({not_before.strftime('%d/%m/%Y')}).",
        )


def mark_done(activity: AgriculturalActivity, actor, done_date: date, captured_at) -> None:
    activity.status = ActivityStatus.DONE
    activity.done_date = done_date
    activity.completed_by = actor
    activity.completed_at = timezone.now()
    activity.captured_at = captured_at
    save_next_version(activity, COMPLETION_FIELDS)


def record_completion(activity: AgriculturalActivity, actor, sent: dict) -> None:
    record_activity_event(
        activity=activity,
        actor=actor,
        action=AgriculturalActivityAuditEvent.Action.COMPLETED,
        before={"status": ActivityStatus.SCHEDULED, "done_date": None, "inputs": None},
        after={
            "status": activity.status,
            "done_date": activity.done_date,
            "inputs": inputs_for_history(sent) or None,
        },
    )
