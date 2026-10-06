from django.db.models import Q, QuerySet

from .access import is_association_admin
from .models import Role, User
from .system_roles import ADMINISTRATOR, PRODUCER

SYSTEM_ROLE_KINDS = Q(kind__in=[Role.Kind.FIXED, Role.Kind.PREDEFINED])


def visible_users(actor) -> QuerySet[User]:
    """Qué cuentas puede ver o administrar `actor`. El backend siempre falla cerrado.

    Un superusuario nunca aparece en el resultado, ni siquiera para otro superusuario: son
    cuentas técnicas, fuera del modelo de negocio.
    """
    base = User.objects.exclude(is_superuser=True)
    if actor.is_superuser:
        return base
    if is_association_admin(actor):
        # Las cuentas de Administrador y Productor son siempre visibles; las de empleado no: la
        # asociación no opera en el espacio de un productor.
        return base.filter(groups__role__code__in=[ADMINISTRATOR, PRODUCER]).distinct()
    if actor.producer_id is not None:
        return base.filter(producer_id=actor.producer_id)
    # Ni superusuario, ni Administrador, ni ligada a un productor: no hay alcance que darle.
    return base.none()


def visible_roles(actor) -> QuerySet[Role]:
    """Qué roles puede ver o asignar `actor`: los del sistema, más los propios de su alcance."""
    # select_related: RoleSerializer expone el productor dueño del rol, y una lista no debe
    # pagar una consulta aparte por cada fila para traerlo.
    # prefetch: RoleSerializer lista los permisos de cada rol con su nombre.
    base = Role.objects.select_related("producer").prefetch_related(
        "group__permissions__content_type"
    )
    if actor.is_superuser:
        return base
    if is_association_admin(actor):
        return base.filter(SYSTEM_ROLE_KINDS)
    if actor.producer_id is not None:
        return base.filter(SYSTEM_ROLE_KINDS | Q(producer_id=actor.producer_id))
    return base.none()


def acts_for_producer(actor, producer_id) -> bool:
    """Si `actor` puede operar en el espacio del productor `producer_id`.

    Solo el superusuario y el propio productor (o sus empleados): la asociación no opera en el
    espacio de un productor.
    """
    if actor.is_superuser:
        return True
    return producer_id is not None and actor.producer_id == producer_id
