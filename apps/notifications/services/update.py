"""Leer y eliminar avisos de la bandeja. Todo es idempotente: repetirlo no cambia nada, así que
el dispositivo puede reintentar sin miedo."""

from django.utils import timezone

from ..exceptions import NotificationNotFound
from .queries import reachable, visible


def _one(notifications, pk):
    found = notifications.filter(pk=pk)
    if not found.exists():
        raise NotificationNotFound()
    return found


def mark_read(actor, pk) -> None:
    # Una eliminada ya no está en la bandeja: no se lee. Leerla otra vez conserva la hora de la
    # primera lectura.
    _one(visible(actor), pk).filter(read_at__isnull=True).update(read_at=timezone.now())


def mark_all_read(actor) -> int:
    return visible(actor).filter(read_at__isnull=True).update(read_at=timezone.now())


def dismiss(actor, pk) -> None:
    _one(reachable(actor), pk).filter(dismissed_at__isnull=True).update(
        dismissed_at=timezone.now()
    )


def restore(actor, pk) -> None:
    _one(reachable(actor), pk).update(dismissed_at=None)


def dismiss_read(actor) -> int:
    return visible(actor).filter(read_at__isnull=False).update(dismissed_at=timezone.now())
