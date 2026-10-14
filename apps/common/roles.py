"""Roles del sistema que más de una app necesita reconocer."""

# Mismos códigos con los que la app de cuentas siembra los roles; se repiten aquí como texto
# porque esta app no importa de ninguna otra.
ADMINISTRATOR_ROLE_CODE = "administrator"
PRODUCER_ROLE_CODE = "producer"


def is_association_admin(user) -> bool:
    """El rol Administrador es exclusivo de la asociación: tenerlo basta, sin mirar permisos."""
    return user.groups.filter(role__code=ADMINISTRATOR_ROLE_CODE).exists()


def is_employee(user) -> bool:
    """Si la cuenta es de un empleado de un productor: tiene productor y algún rol que no es el
    de Productor.

    Se decide por los roles y no por la finca: un empleado sin finca asignada sigue siendo un
    empleado, y por eso no alcanza ninguna. Una cuenta con productor y sin ningún rol no existe
    en el negocio (toda cuenta nace con uno) y tampoco tiene permisos con los que llegar a nada.
    """
    if user.is_superuser or user.producer_id is None:
        return False
    return user.groups.filter(role__isnull=False).exclude(role__code=PRODUCER_ROLE_CODE).exists()
