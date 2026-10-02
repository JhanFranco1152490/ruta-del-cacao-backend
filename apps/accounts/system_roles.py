from django.contrib.auth.models import Group, Permission

from .models import Role

ADMINISTRATOR = "administrator"
PRODUCER = "producer"
FOREMAN = "foreman"
QUALITY_MANAGER = "quality_manager"
SALES_MANAGER = "sales_manager"

# Los permisos de administración (`users_*`, `roles_*`) son delegables (ver `registry.py`):
# un productor puede querer un administrador de confianza que haga la mayor parte de su
# trabajo. `association_access_manage` no es delegable y solo lo tiene el rol Productor: es la
# salvaguarda que protege esa cuenta de cualquier empleado, por más permisos que tenga.
SYSTEM_ROLES = {
    ADMINISTRATOR: {
        "kind": Role.Kind.FIXED,
        "name": "Administrador",
        "permissions": [
            "accounts.users_view",
            "accounts.users_create",
            "accounts.users_update",
            "accounts.users_change_status",
            "accounts.roles_view",
            "accounts.roles_manage",
            "producers.view",
            "producers.create",
            "producers.update",
            "producers.change_status",
            # La asociación lee las fincas de todos los productores: nombre y ubicación son la
            # base de sus reportes. Registrarlas, editarlas o eliminarlas es solo del productor y
            # de los empleados a los que él se lo delegue.
            "farms.view_farm",
        ],
    },
    PRODUCER: {
        "kind": Role.Kind.FIXED,
        "name": "Productor",
        "permissions": [
            "accounts.users_view",
            "accounts.users_create",
            "accounts.users_update",
            "accounts.users_change_status",
            "accounts.roles_view",
            "accounts.roles_manage",
            "accounts.association_access_manage",
            "farms.view_farm",
            "farms.add_farm",
            "farms.change_farm",
            "farms.delete_farm",
        ],
    },
    FOREMAN: {"kind": Role.Kind.PREDEFINED, "name": "Capataz/Operario", "permissions": []},
    QUALITY_MANAGER: {
        "kind": Role.Kind.PREDEFINED,
        "name": "Encargado de calidad",
        "permissions": [],
    },
    SALES_MANAGER: {"kind": Role.Kind.PREDEFINED, "name": "Comercializador", "permissions": []},
}


def _permission(code: str) -> Permission:
    app_label, codename = code.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def sync_system_roles() -> None:
    """Crea los roles del sistema que falten y deja sus permisos como los declara el código.

    Nunca toca un rol propio (`kind=custom`): busca y crea solo por `code`, que los propios no
    tienen. Se conecta al `post_migrate` de la última app instalada (ver `apps.py`): para
    entonces ya existen los permisos de todas las apps que usan los roles.
    """
    for code, definition in SYSTEM_ROLES.items():
        role = Role.objects.filter(code=code).first()
        if role is None:
            group = Group.objects.create(name=f"role-{code}")
            role = Role.objects.create(
                code=code,
                kind=definition["kind"],
                name=definition["name"],
                group=group,
            )
        role.group.permissions.set(
            _permission(permission_code) for permission_code in definition["permissions"]
        )


def get_system_role(code: str) -> Role:
    return Role.objects.get(code=code)
