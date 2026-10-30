from django.utils import timezone

from ..models import Notification


def resolve_notifications(lot_id, kinds) -> int:
    """Marca como resueltos los avisos de un lote de esos tipos que todavía no lo están, para
    todas las personas que los recibieron. Uno ya resuelto conserva su hora: es cuándo llegó el
    registro que faltaba."""
    return Notification.objects.filter(
        lot_id=lot_id, kind__in=kinds, resolved_at__isnull=True
    ).update(resolved_at=timezone.now())


def withdraw_notifications(kinds, *, fermentation_turn_id=None, drying_log_id=None) -> int:
    """Borra los avisos de esos tipos de un volteo o de una bitácora que ya no cumple su condición.

    Se borran y no se ocultan: un aviso que existe, aunque esté oculto, cuenta como ya avisado, y
    una corrección que vuelve a cumplir la condición no avisaría otra vez."""
    record = (
        {"fermentation_turn_id": fermentation_turn_id}
        if fermentation_turn_id is not None
        else {"drying_log_id": drying_log_id}
    )
    deleted, _ = Notification.objects.filter(kind__in=kinds, **record).delete()
    return deleted
