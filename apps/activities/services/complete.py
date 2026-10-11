from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.versioning import save_next_version

from ..choices import ActivityStatus, ActivityType
from ..exceptions import (
    ActivityAlreadyDone,
    InputInactive,
    InvalidActivity,
    MonitoringRequiresResult,
)
from ..models import (
    AgriculturalActivity,
    AgriculturalActivityAuditEvent,
    AgriculturalActivityInput,
)
from ..state import today_in_bogota
from . import queries
from .audit import record_activity_event

COMPLETION_FIELDS = ["status", "done_date", "completed_by", "completed_at", "captured_at"]
QUANTITY_PLACES = Decimal("0.001")

# El modelo del insumo se toma de la relación y no de su app: ninguna app importa de otra.
AgriculturalInput = AgriculturalActivityInput._meta.get_field("input").related_model


@transaction.atomic
def complete_activity(actor, activity_id, data: dict) -> tuple[AgriculturalActivity, bool]:
    """Registra que la labor se hizo, con los insumos que gastó. Devuelve `(actividad, cambió)`.

    Llega desde la cola del dispositivo, a veces horas después: no pide versión, porque lo que
    importa es que la actividad siga sin realizar (si la reprogramaron entretanto, la labor igual
    se hizo). El mismo registro reenviado responde sin escribir nada ni volver a descontar.
    """
    sent = _sent_inputs(data.get("inputs") or [])
    activity = queries.lock_activity(actor, activity_id)
    if activity.status == ActivityStatus.DONE:
        if activity.done_date == data["done_date"] and _used_inputs(activity) == sent:
            return activity, False
        raise ActivityAlreadyDone()
    if activity.activity_type == ActivityType.PHYTOSANITARY_MONITORING:
        raise MonitoringRequiresResult()
    if sent and activity.activity_type == ActivityType.INVENTORY:
        # El conteo se registra en el inventario: descontar aquí lo contaría dos veces.
        raise InvalidActivity("inputs", "Una actividad de inventario no registra insumos.")
    _ensure_valid_date(activity, data["done_date"])
    items = _locked_inputs(activity, sent)

    activity.status = ActivityStatus.DONE
    activity.done_date = data["done_date"]
    activity.completed_by = actor
    activity.completed_at = timezone.now()
    activity.captured_at = data.get("captured_at")
    save_next_version(activity, COMPLETION_FIELDS)
    _discount_inputs(activity, items, sent, actor)
    record_activity_event(
        activity=activity,
        actor=actor,
        action=AgriculturalActivityAuditEvent.Action.COMPLETED,
        before={"status": ActivityStatus.SCHEDULED, "done_date": None, "inputs": None},
        after={
            "status": activity.status,
            "done_date": activity.done_date,
            "inputs": _inputs_for_history(sent) or None,
        },
    )
    return activity, True


def _sent_inputs(rows) -> dict:
    """`{id del insumo: cantidad}`, con la cantidad en tres decimales, como se guarda."""
    sent = {}
    for row in rows:
        input_id = str(row["input_id"])
        if input_id in sent:
            raise InvalidActivity("inputs", "Este insumo ya está en la lista.")
        quantity = Decimal(str(row["quantity"]))
        if quantity <= 0:
            raise InvalidActivity("inputs", "La cantidad debe ser mayor que cero.")
        sent[input_id] = quantity.quantize(QUANTITY_PLACES)
    return sent


def _used_inputs(activity: AgriculturalActivity) -> dict:
    return {str(row.input_id): row.quantity for row in activity.inputs.all()}


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


def _locked_inputs(activity: AgriculturalActivity, sent: dict) -> dict:
    """Los insumos enviados, bloqueados en orden de id (después de la finca y antes de sus
    existencias, el orden que también sigue el inventario), para no cruzarse con su
    desactivación ni con otra labor que gaste los mismos."""
    if not sent:
        return {}
    items = {
        str(item.pk): item
        for item in AgriculturalInput.objects.select_for_update()
        .filter(pk__in=sent.keys(), producer_id=activity.plot.farm.producer_id)
        .order_by("pk")
    }
    if len(items) != len(sent):
        # Un 400 y no un 404: la cola leería un 404 como una actividad eliminada y descartaría el
        # registro. Así llega a la bandeja y la persona elige otro insumo.
        raise InvalidActivity("inputs", "El insumo no existe en el catálogo del productor.")
    inactive = sorted(input_id for input_id, item in items.items() if not item.is_active)
    if inactive:
        raise InputInactive(inactive)
    return items


def _discount_inputs(activity: AgriculturalActivity, items: dict, sent: dict, actor) -> None:
    note = _note(activity)
    for input_id, quantity in sent.items():
        item = items[input_id]
        movement = item.record_consumption(
            activity.plot.farm, quantity, activity.done_date, note, actor
        )
        AgriculturalActivityInput.objects.create(
            activity=activity, input=item, quantity=quantity, stock_movement=movement
        )


def _note(activity: AgriculturalActivity) -> str:
    """De qué labor viene la salida, como la muestra el inventario: "Fertilización · P-03"."""
    if activity.activity_type == ActivityType.OTHER:
        task = activity.other_description
    else:
        task = ActivityType(activity.activity_type).label
    return f"{task} · {activity.plot.code}"


def _inputs_for_history(sent: dict) -> list[dict]:
    return [
        {"input_id": input_id, "quantity": f"{quantity:.3f}"}
        for input_id, quantity in sorted(sent.items())
    ]
