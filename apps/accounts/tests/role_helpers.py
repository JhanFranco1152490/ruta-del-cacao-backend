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


def make_delegate(producer, permission_codes, farm=None, farms=(), all_farms=False):
    """Empleado con un rol propio a medida: el "delegado" al que un productor le da permisos.
    Trabaja en `farm` o en las `farms`, o en todas con `all_farms`; sin ninguna no alcanza nada de
    campo, como todo empleado sin alcance."""
    role = RoleFactory(producer=producer, permissions=permission_codes)
    worked = [*farms, *([farm] if farm is not None else [])]
    return grant_role(UserFactory(producer=producer, farms=worked, all_farms=all_farms), role)
