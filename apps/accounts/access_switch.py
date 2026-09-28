from django.db import transaction
from django.utils import timezone

from .events import record_account_event
from .exceptions import AssociationAccessNotFound
from .models import AccountManagementEvent, AssociationAccess


def _own_producer_id(actor):
    if actor.producer_id is None:
        raise AssociationAccessNotFound()
    return actor.producer_id


def get_association_access(actor) -> AssociationAccess:
    producer_id = _own_producer_id(actor)
    access = AssociationAccess.objects.filter(producer_id=producer_id).first()
    if access is None:
        # La ausencia de fila equivale a apagado (ver el modelo): no se crea una fila por una
        # simple consulta.
        return AssociationAccess(producer_id=producer_id, enabled=False, changed_at=None)
    return access


def set_association_access(actor, enabled: bool, request_id) -> AssociationAccess:
    producer_id = _own_producer_id(actor)

    with transaction.atomic():
        # get_or_create resuelve sola la carrera de dos encendidos simultáneos del mismo
        # productor (reintenta si otra transacción crea la fila primero); el bloqueo explícito
        # que sigue evita perder un cambio entre leer y comparar el valor actual.
        AssociationAccess.objects.get_or_create(producer_id=producer_id)
        access = AssociationAccess.objects.select_for_update().get(pk=producer_id)
        if access.enabled == enabled:
            # Repetir el valor no cambia nada ni genera evento.
            return access

        access.enabled = enabled
        access.changed_by = actor
        access.changed_at = timezone.now()
        access.save(update_fields=["enabled", "changed_by", "changed_at"])
        record_account_event(
            (
                AccountManagementEvent.EventType.ASSOCIATION_ACCESS_ENABLED
                if enabled
                else AccountManagementEvent.EventType.ASSOCIATION_ACCESS_DISABLED
            ),
            request_id,
            actor=actor,
        )
    return access
