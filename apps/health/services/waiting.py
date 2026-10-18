from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.common.locks import lock_aggregate_root

from ..exceptions import DetectionNotFound
from ..models import Detection
from .shared import DETECTION_FARM, detection_scope


def detections_without_control(actor, producer_id=None) -> QuerySet[Detection]:
    """Las detecciones en que alguien pidió que le programen un control y nadie lo ha atendido
    (ni programado ni decidido que no requiere), del monitoreo más antiguo al más reciente, en las
    fincas que alcanza `actor`. Quien registra un monitoreo y no puede programar lo pide, y quien
    programa tiene que enterarse. "Ninguno por ahora" no avisa: no se pidió nada. Sin fecha
    mínima: una solicitud vieja no debe perderse. `producer_id` solo lo usa la cuenta técnica."""
    detections = Detection.objects.filter(
        treatments__isnull=True,
        control_requested_at__isnull=False,
        control_dismissed_at__isnull=True,
        **detection_scope(actor),
    )
    if actor.is_superuser and producer_id is not None:
        detections = detections.filter(monitoring__activity__plot__farm__producer_id=producer_id)
    return detections.select_related(
        "pest_disease", "monitoring__activity__plot__farm", "control_requested_by"
    ).order_by("monitoring__activity__done_date", "id")


@transaction.atomic
def dismiss_control(actor, detection_id) -> None:
    """Quien programa decide que la detección no requiere control: sale del aviso y queda
    registrado quién lo decidió y cuándo. Repetirlo no cambia quién lo decidió primero."""
    detection, _ = lock_aggregate_root(
        Detection,
        detection_id,
        root=DETECTION_FARM,
        scope=detection_scope(actor),
        not_found=DetectionNotFound,
    )
    if detection.control_dismissed_at is not None:
        return
    detection.control_dismissed_by = actor
    detection.control_dismissed_at = timezone.now()
    detection.save(update_fields=["control_dismissed_by", "control_dismissed_at"])
