from django.db.models import Q, QuerySet

from .access import is_association_admin
from .models import AssociationAccess, Role, User
from .system_roles import ADMINISTRATOR, PRODUCER

SYSTEM_ROLE_KINDS = Q(kind__in=[Role.Kind.FIXED, Role.Kind.PREDEFINED])


def _producers_with_access() -> QuerySet:
    return AssociationAccess.objects.filter(enabled=True).values_list("producer_id", flat=True)


def visible_users(actor) -> QuerySet[User]:
    """Qué cuentas puede ver o administrar `actor`. El backend siempre falla cerrado.

    Un superusuario nunca aparece en el resultado, ni siquiera para otro superusuario: son
    cuentas técnicas, fuera del modelo de negocio.
    """
    base = User.objects.exclude(is_superuser=True)
    if actor.is_superuser:
        return base
    if is_association_admin(actor):
        # Las cuentas de Administrador y Productor son siempre visibles; las de empleado,
        # solo si el productor del que dependen encendió el interruptor de la asociación.
        return base.filter(
            Q(groups__role__code__in=[ADMINISTRATOR, PRODUCER])
            | Q(producer_id__in=_producers_with_access())
        ).distinct()
    if actor.producer_id is not None:
        return base.filter(producer_id=actor.producer_id)
    # Ni superusuario, ni Administrador, ni ligada a un productor: no hay alcance que darle.
    return base.none()


def visible_roles(actor) -> QuerySet[Role]:
    """Qué roles puede ver o asignar `actor`: los del sistema, más los propios de su alcance."""
    if actor.is_superuser:
        return Role.objects.all()
    if is_association_admin(actor):
        return Role.objects.filter(SYSTEM_ROLE_KINDS | Q(producer_id__in=_producers_with_access()))
    if actor.producer_id is not None:
        return Role.objects.filter(SYSTEM_ROLE_KINDS | Q(producer_id=actor.producer_id))
    return Role.objects.none()


def acts_for_producer(actor, producer_id) -> bool:
    """Si `actor` puede operar en el espacio del productor `producer_id`."""
    if actor.is_superuser:
        return True
    if producer_id is not None and actor.producer_id == producer_id:
        return True
    if is_association_admin(actor):
        return AssociationAccess.objects.filter(producer_id=producer_id, enabled=True).exists()
    return False
