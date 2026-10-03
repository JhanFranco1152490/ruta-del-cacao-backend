"""Roles del sistema que más de una app necesita reconocer."""

# Mismo código con el que la app de cuentas siembra el rol; se repite aquí como texto porque
# esta app no importa de ninguna otra.
ADMINISTRATOR_ROLE_CODE = "administrator"


def is_association_admin(user) -> bool:
    """El rol Administrador es exclusivo de la asociación: tenerlo basta, sin mirar permisos."""
    return user.groups.filter(role__code=ADMINISTRATOR_ROLE_CODE).exists()
