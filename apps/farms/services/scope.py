from django.db.models import QuerySet

from apps.common.roles import is_association_admin

from ..models import Farm


def readable_farms(actor) -> QuerySet[Farm]:
    """Qué fincas puede consultar `actor`. Falla cerrado: sin productor ni rol de la
    asociación, ninguna.

    La asociación y la cuenta técnica leen las de todos los productores: nombre y ubicación de las
    fincas son la base de sus reportes. Crear o editar no pasa por aquí.
    """
    if actor.is_superuser or is_association_admin(actor):
        return Farm.objects.select_related("producer")
    if actor.producer_id is not None:
        return Farm.objects.select_related("producer").filter(producer_id=actor.producer_id)
    return Farm.objects.none()
