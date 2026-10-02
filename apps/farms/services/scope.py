from django.db.models import QuerySet

from apps.common.roles import is_association_admin

from ..models import Farm

# Interruptor de acceso de la asociación (HU-03), consultado a través de la relación inversa
# que tiene el productor. Así esta app no importa el modelo de la app de cuentas.
ASSOCIATION_ACCESS_ENABLED = "association_access__enabled"


def reads_every_producer(actor) -> bool:
    return actor.is_superuser or is_association_admin(actor)


def readable_farms(actor) -> QuerySet[Farm]:
    """Qué fincas puede consultar `actor`. Falla cerrado: sin productor ni rol de la
    asociación, ninguna.

    La asociación lee las de todos los productores sin depender del interruptor de acceso:
    nombre y ubicación de las fincas son la base de sus reportes. Crear o editar no pasa por
    aquí, sino por `managed_farms`.
    """
    if reads_every_producer(actor):
        return Farm.objects.all()
    if actor.producer_id is not None:
        return Farm.objects.filter(producer_id=actor.producer_id)
    return Farm.objects.none()


def managed_farms(actor) -> QuerySet[Farm]:
    """Qué fincas puede gestionar `actor` (editar, activar, desactivar). La asociación solo
    gestiona las de productores que encendieron el interruptor: es una función en el espacio
    del productor, y abrirlo es decisión de él."""
    if actor.is_superuser:
        return Farm.objects.all()
    if is_association_admin(actor):
        return Farm.objects.filter(**{f"producer__{ASSOCIATION_ACCESS_ENABLED}": True})
    if actor.producer_id is not None:
        return Farm.objects.filter(producer_id=actor.producer_id)
    return Farm.objects.none()


def can_manage_producer(actor, producer_id) -> bool:
    """Si `actor` puede gestionar fincas del productor `producer_id` (que debe existir)."""
    if actor.is_superuser:
        return True
    if is_association_admin(actor):
        return (
            producer_model()
            .objects.filter(pk=producer_id, **{ASSOCIATION_ACCESS_ENABLED: True})
            .exists()
        )
    return actor.producer_id is not None and actor.producer_id == producer_id


def producer_model():
    # `Producer` sin importarlo: se obtiene de la relación que ya declara `Farm`.
    return Farm._meta.get_field("producer").related_model
