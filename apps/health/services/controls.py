"""Los controles fitosanitarios: una actividad unida a la detección que atiende.

Se crean en la planilla del monitoreo (hecho en el momento o programado para después) o desde una
detección ya registrada. La actividad la crea la app de actividades con sus reglas (fecha,
responsable, insumos); aquí va el vínculo con la detección y qué se hizo o se piensa hacer.
"""

from decimal import Decimal

from django.db import transaction

from apps.common.locks import lock_aggregate_root

from ..choices import ControlMethod, ControlMode
from ..exceptions import (
    ControlIdConflict,
    DetectionNotFound,
    DoneControlNotAllowed,
    InvalidResult,
    PlannedInputInactive,
    ScheduleNotAllowed,
)
from ..models import Detection, PhytosanitaryTreatment
from .shared import (
    ACTIVITY_DONE,
    COMPLETE_PERMISSION,
    DETECTION_FARM,
    SCHEDULE_PERMISSION,
    AgriculturalActivity,
    detection_scope,
)

# El modelo del insumo se toma de la relación y no de su app: ninguna app importa de otra.
AgriculturalInput = PhytosanitaryTreatment._meta.get_field("planned_input").related_model


def clean_control(control: dict) -> dict:
    """El control con qué se hizo validado: obligatorio en uno realizado, y la descripción solo
    con "Otro"."""
    method = control["method"]
    description = (control["method_description"] or "").strip() or None
    done = control["mode"] == ControlMode.DONE
    if done and method is None:
        raise InvalidResult("method", "Indica qué hiciste.")
    if method == ControlMethod.OTHER and description is None:
        raise InvalidResult("method_description", "Escribe qué se hizo.")
    if method != ControlMethod.OTHER and description is not None:
        raise InvalidResult(
            "method_description", "Solo un control de tipo Otro lleva descripción."
        )
    if done and method == ControlMethod.PRODUCT_APPLICATION and not control["inputs"]:
        raise InvalidResult("inputs", "Agrega el producto que aplicaste.")
    return {**control, "method_description": description}


def add_control(actor, detection: Detection, monitoring_activity, control: dict):
    """Crea el control y su vínculo con la detección. `control` ya pasó por `clean_control` y,
    si es realizado, trae su fecha y su responsable. La finca ya está bloqueada."""
    plot = monitoring_activity.plot
    if control["mode"] == ControlMode.SCHEDULED:
        if not actor.has_perm(SCHEDULE_PERMISSION):
            raise ScheduleNotAllowed()
        planned_input = _planned_input(plot, control["planned_input_id"])
        activity = AgriculturalActivity.schedule_control(
            actor, plot, control["id"], control["scheduled_date"], control["assignee_id"]
        )
    else:
        planned_input = None
        activity = AgriculturalActivity.record_done_control(
            actor,
            plot,
            control["id"],
            control["done_date"],
            not_before=monitoring_activity.done_date,
            assignee_id=control["assignee_id"],
            inputs=control["inputs"],
            captured_at=control.get("captured_at"),
        )
    PhytosanitaryTreatment.objects.create(
        activity=activity,
        detection=detection,
        planned_input=planned_input,
        method=control["method"],
        method_description=control["method_description"],
    )
    return activity


def treatment_values(treatment: PhytosanitaryTreatment) -> tuple:
    """Lo propio de un control, que no cambia al editarlo como actividad: con esto se reconoce un
    reenvío."""
    return (
        treatment.detection_id,
        treatment.method,
        treatment.method_description,
        treatment.planned_input_id,
    )


@transaction.atomic
def create_control_from_detection(actor, detection_id, data: dict):
    """Programa o registra un control desde una detección ya registrada. Devuelve `(actividad,
    creada)`: el mismo control reenviado con su `id` responde sin duplicarlo."""
    detection, _ = lock_aggregate_root(
        Detection,
        detection_id,
        root=DETECTION_FARM,
        scope=detection_scope(actor),
        not_found=DetectionNotFound,
    )
    if data["mode"] == ControlMode.DONE and not actor.has_perm(COMPLETE_PERMISSION):
        raise DoneControlNotAllowed()
    control = clean_control(data)
    existing = (
        PhytosanitaryTreatment.objects.select_related("activity").filter(pk=control["id"]).first()
    )
    if existing is not None:
        if _same_control(existing, detection, control):
            return existing.activity, False
        raise ControlIdConflict()

    monitoring_activity = detection.monitoring.activity
    activity = add_control(actor, detection, monitoring_activity, control)
    return activity, True


def _planned_input(plot, input_id):
    if input_id is None:
        return None
    # Bloqueado después de la finca, el orden que sigue el inventario: así no se desactiva ni se
    # elimina mientras se guarda el control que lo nombra.
    item = (
        AgriculturalInput.objects.select_for_update()
        .filter(pk=input_id, producer_id=plot.farm.producer_id)
        .first()
    )
    if item is None:
        # Un 400 y no un 404: la cola leería un 404 como una detección eliminada.
        raise InvalidResult(
            "planned_input_id", "El insumo no existe en el catálogo del productor."
        )
    if not item.is_active:
        raise PlannedInputInactive(item.pk)
    return item


def _same_control(existing: PhytosanitaryTreatment, detection, control: dict) -> bool:
    activity = existing.activity
    sent = (
        detection.pk,
        control["method"],
        control["method_description"],
        control["planned_input_id"],
    )
    if treatment_values(existing) != sent:
        return False
    if control["mode"] == ControlMode.SCHEDULED:
        return activity.status != ACTIVITY_DONE and (
            activity.scheduled_date,
            str(activity.assignee_id),
        ) == (control["scheduled_date"], str(control["assignee_id"]))
    used = {str(row.input_id): row.quantity for row in activity.inputs.all()}
    sent_inputs = {
        str(row["input_id"]): Decimal(str(row["quantity"])) for row in control["inputs"]
    }
    return (
        activity.status == ACTIVITY_DONE
        and (activity.done_date, str(activity.assignee_id))
        == (control["done_date"], str(control["assignee_id"]))
        and used == sent_inputs
    )
