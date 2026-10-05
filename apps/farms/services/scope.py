from django.db.models import QuerySet

from apps.common.roles import is_association_admin

from ..models import Farm


def readable_farms(actor) -> QuerySet[Farm]:
    """Qué fincas puede consultar `actor`. Falla cerrado: sin productor ni rol de la
    asociación, ninguna.

    La asociación lee las de todos los productores: nombre y ubicación de las fincas son la base
    de sus reportes. Un superusuario que eligió un productor ve las de ese productor, como las
    vería él; sin elegir, las de todos. Crear o editar no pasa por aquí.
    """
    if actor.effective_producer_id is not None:
        return Farm.objects.filter(producer_id=actor.effective_producer_id)
    if actor.is_superuser or is_association_admin(actor):
        return Farm.objects.all()
    return Farm.objects.none()
