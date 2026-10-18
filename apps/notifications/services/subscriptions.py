from django.conf import settings
from django.db import transaction

from ..models import PushSubscription
from ..push.send import push_enabled


def public_key() -> str | None:
    """La llave que el navegador usa para suscribirse, solo si el servidor puede enviar: ofrecer
    activar los avisos sin poder mandarlos dejaría a la persona esperando algo que no llega."""
    return settings.VAPID_PUBLIC_KEY if push_enabled() else None


def subscribe(actor, data) -> tuple[PushSubscription, bool]:
    """Guarda el dispositivo de `actor` y dice si es nuevo. La dirección identifica al
    dispositivo: si ya estaba, se actualizan sus llaves, y si era de otra cuenta (otra persona
    inició sesión en ese navegador sin cerrar la suya), pasa a la cuenta actual, que es la que
    lo está usando."""
    with transaction.atomic():
        return PushSubscription.objects.update_or_create(
            endpoint=data["endpoint"],
            defaults={
                "user": actor,
                "p256dh": data["keys"]["p256dh"],
                "auth": data["keys"]["auth"],
                "device_label": data.get("device_label") or None,
            },
        )


def unsubscribe(actor, endpoint) -> None:
    # Solo el propio: nadie apaga los avisos del dispositivo de otro.
    PushSubscription.objects.filter(user=actor, endpoint=endpoint).delete()
