"""Enviar las push de los avisos nuevos.

Corre al final de cada evaluación. Toma los avisos nuevos (sin leer, sin eliminar, de las últimas
24 horas y de alguien con algún dispositivo), arma una push por persona y la manda a cada uno de
sus dispositivos. Solo de 6:00 a 19:00 en Bogotá: los avisos nacen a medianoche, cuando cambia la
fecha, y un teléfono que suena a esa hora hace que la persona bloquee las notificaciones.
"""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from pywebpush import WebPushException, webpush
from requests import RequestException

from ..models import Notification, PushSubscription
from .messages import push_message

logger = logging.getLogger(__name__)

PUSH_START_HOUR = 6
PUSH_END_HOUR = 19
# Un aviso que no salió en un día ya no se manda: la persona lo ve en la bandeja.
PUSH_WINDOW = timedelta(hours=24)
# Cuánto guarda el servicio de push un aviso para un teléfono sin señal.
PUSH_TTL_SECONDS = 12 * 60 * 60
PUSH_TIMEOUT_SECONDS = 10
# El servicio de push dice que el dispositivo ya no existe (desinstalaron la app o quitaron el
# permiso): se olvida.
GONE_STATUSES = {404, 410}


@dataclass
class SendResult:
    sent: int = 0
    failed: int = 0


def push_enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_pending_pushes(now) -> SendResult:
    result = SendResult()
    if not push_enabled():
        return result
    # Una cuenta desactivada no recibe nada: sus dispositivos se olvidan.
    PushSubscription.objects.filter(user__is_active=False).delete()
    if not PUSH_START_HOUR <= timezone.localtime(now).hour < PUSH_END_HOUR:
        return result

    claimed = claim_pending(now)
    by_recipient: dict = {}
    for notification in claimed:
        by_recipient.setdefault(notification.recipient_id, []).append(notification)
    devices: dict = {}
    for device in PushSubscription.objects.filter(user_id__in=by_recipient):
        devices.setdefault(device.user_id, []).append(device)

    today = timezone.localdate(now)
    for recipient_id, notifications in by_recipient.items():
        payload = json.dumps(push_message(notifications, recipient_id, today))
        delivered = False
        for device in devices.get(recipient_id, []):
            if _deliver(device, payload, now, result):
                delivered = True
        if not delivered:
            # Ningún dispositivo lo recibió: la siguiente hora se vuelve a intentar.
            Notification.objects.filter(pk__in=[n.pk for n in notifications]).update(
                pushed_at=None
            )
    return result


def claim_pending(now) -> list[Notification]:
    """Toma los avisos por enviar y los marca enviados en la misma transacción. Las filas que
    otra evaluación ya está tomando se saltan: dos evaluaciones a la vez no mandan dos veces la
    misma push."""
    with transaction.atomic():
        ids = list(
            Notification.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(
                Exists(PushSubscription.objects.filter(user_id=OuterRef("recipient_id"))),
                pushed_at__isnull=True,
                read_at__isnull=True,
                dismissed_at__isnull=True,
                created_at__gte=now - PUSH_WINDOW,
                recipient__is_active=True,
            )
            .values_list("pk", flat=True)
        )
        Notification.objects.filter(pk__in=ids).update(pushed_at=now)
    return list(
        Notification.objects.filter(pk__in=ids).select_related(
            "activity__plot__farm", "detection__pest_disease"
        )
    )


def _deliver(device, payload, now, result) -> bool:
    try:
        webpush(
            subscription_info={
                "endpoint": device.endpoint,
                "keys": {"p256dh": device.p256dh, "auth": device.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            # Un diccionario nuevo en cada envío: la librería le agrega la audiencia y el
            # vencimiento del dispositivo al que va.
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=PUSH_TTL_SECONDS,
            timeout=PUSH_TIMEOUT_SECONDS,
        )
    except (WebPushException, RequestException) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in GONE_STATUSES:
            device.delete()
            return False
        # Sin la dirección ni el mensaje: los dos identifican al dispositivo.
        logger.warning("Push no enviada: %s %s", type(exc).__name__, status or "")
        result.failed += 1
        return False
    device.last_success_at = now
    device.save(update_fields=["last_success_at"])
    result.sent += 1
    return True
