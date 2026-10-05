from apps.accounts.system_roles import ADMINISTRATOR, PRODUCER, get_system_role

from .factories import RoleFactory, UserFactory


def grant_role(user, role):
    """Asigna un rol ya existente (del sistema o propio) a una cuenta de prueba."""
    user.groups.add(role.group)
    return user


def make_administrator():
    return grant_role(UserFactory(), get_system_role(ADMINISTRATOR))


def make_producer_owner(producer):
    return grant_role(UserFactory(producer=producer), get_system_role(PRODUCER))


def make_delegate(producer, permission_codes):
    """Empleado con un rol propio a medida: el "delegado" al que un productor le da permisos."""
    role = RoleFactory(producer=producer, permissions=permission_codes)
    return grant_role(UserFactory(producer=producer), role)
