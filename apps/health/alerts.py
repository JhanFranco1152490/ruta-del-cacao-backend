"""El aviso de control pendiente: una detección en la que alguien pidió un control y nadie lo ha
programado ni decidido que no hace falta.

Recuerda cada día durante los primeros diez días desde la solicitud, a quien puede programarlo en
esa finca. La clave lleva el día, así que el aviso de hoy reemplaza al de ayer. Pasados los diez
días deja de sonar: la solicitud sigue en el aviso de detecciones que esperan un control.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.common.alerts import NotificationDraft
from apps.common.schedulers import Schedulers

from .models import Detection

# Cuántos días, contando el de la solicitud, se recuerda un control pedido.
CONTROL_PENDING_DAYS = 10


def evaluate(today):
    # Los días se cuentan con la fecha de Bogotá de la solicitud, no con la UTC.
    first_day = today - timedelta(days=CONTROL_PENDING_DAYS - 1)
    detections = list(
        Detection.objects.filter(
            control_requested_at__gte=_start_of(first_day),
            control_requested_at__lt=_start_of(today + timedelta(days=1)),
            control_dismissed_at__isnull=True,
            treatments__isnull=True,
        ).select_related("monitoring__activity__plot__farm")
    )
    schedulers = Schedulers({d.monitoring.activity.plot.farm.producer_id for d in detections})

    for detection in detections:
        activity = detection.monitoring.activity
        day = (today - timezone.localdate(detection.control_requested_at)).days
        for recipient_id in schedulers.on_farm(
            activity.plot.farm.producer_id, activity.plot.farm_id
        ):
            yield NotificationDraft(
                recipient_id=recipient_id,
                kind="detection_control_pending",
                condition_key=f"{detection.pk}:{day}",
                thread_key=f"detection:{detection.pk}",
                activity_id=activity.pk,
                detection_id=detection.pk,
            )


def _start_of(day):
    return timezone.make_aware(datetime.combine(day, time.min))
