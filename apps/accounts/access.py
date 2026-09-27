from .system_roles import ADMINISTRATOR


def is_effectively_active(user) -> bool:
    """Una cuenta inactiva, o vinculada a un productor inactivo, no está efectivamente activa.

    Se comprueba en el inicio de sesión, al renovar y en cada solicitud autenticada, para que
    desactivar un productor corte el acceso de sus cuentas sin tocarlas una por una.
    """
    if not user.is_active:
        return False
    if user.producer_id is None:
        return True
    # "active" es el valor de `Producer.Status.ACTIVE`: no se importa el modelo de producers
    # (esta app no importa de otra), igual que los códigos "producers.*" de system_roles.py.
    return user.producer.status == "active"


def is_association_admin(user) -> bool:
    """El rol Administrador es exclusivo (HU-03): tenerlo basta, no hace falta el permiso."""
    return user.groups.filter(role__code=ADMINISTRATOR).exists()
