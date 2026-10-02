from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionInfo:
    area: str
    delegable: bool


# Todo permiso que el catálogo de `/api/permissions` expone (y arma los roles del sistema en
# `system_roles.py`) se declara aquí, con el área que agrupa su catálogo en el frontend y si un
# productor puede delegarlo en sus roles propios.
#
# Regla al agregar un permiso: si actúa sobre el espacio de un productor (sus fincas, sus
# cuentas, su operación), es delegable, porque el productor decide en qué empleado de
# confianza apoyarse. Solo se marca `delegable=False` con la razón escrita al lado: por ejemplo,
# que actúe sobre toda la asociación o que proteja la propia cuenta Productor.
#
# Un código ausente sí es no delegable: la salvaguarda falla cerrado ante un permiso nuevo que
# nadie clasificó todavía. Eso protege contra un olvido; no es la forma de decidir que algo no
# se delega.
PERMISSION_REGISTRY: dict[str, PermissionInfo] = {
    "accounts.users_view": PermissionInfo(area="users", delegable=True),
    "accounts.users_create": PermissionInfo(area="users", delegable=True),
    "accounts.users_update": PermissionInfo(area="users", delegable=True),
    "accounts.users_change_status": PermissionInfo(area="users", delegable=True),
    "accounts.roles_view": PermissionInfo(area="roles", delegable=True),
    "accounts.roles_manage": PermissionInfo(area="roles", delegable=True),
    # No delegable: es lo que impide que un empleado alcance a la cuenta Productor (nadie
    # administra a quien tiene un permiso que él no tiene), y abre el espacio del productor a
    # la asociación, una decisión que solo le corresponde al productor.
    "accounts.association_access_manage": PermissionInfo(
        area="association_access", delegable=False
    ),
    # No delegables: administran a todos los productores de la asociación, no el espacio de uno.
    "producers.view": PermissionInfo(area="producers", delegable=False),
    "producers.create": PermissionInfo(area="producers", delegable=False),
    "producers.update": PermissionInfo(area="producers", delegable=False),
    "producers.change_status": PermissionInfo(area="producers", delegable=False),
    "farms.view_farm": PermissionInfo(area="farms", delegable=True),
    "farms.add_farm": PermissionInfo(area="farms", delegable=True),
    "farms.change_farm": PermissionInfo(area="farms", delegable=True),
    "farms.delete_farm": PermissionInfo(area="farms", delegable=True),
}


def is_delegable(code: str) -> bool:
    info = PERMISSION_REGISTRY.get(code)
    return info is not None and info.delegable


def area_of(code: str) -> str:
    info = PERMISSION_REGISTRY.get(code)
    if info is not None:
        return info.area
    # Un permiso fuera del registro no tiene área declarada: se agrupa por la app que lo
    # define ("app_label.codename"), que sigue siendo una agrupación con sentido para mostrar.
    return code.split(".", 1)[0]


# Un permiso de acción sin su "view" no tiene con qué consultar lo que modifica: quien lo
# tiene queda dependiendo por completo de otra persona para revisar su propio trabajo. Un rol
# propio que pide el de la izquierda recibe siempre el de la derecha también.
PERMISSION_DEPENDENCIES: dict[str, str] = {
    "accounts.users_create": "accounts.users_view",
    "accounts.users_update": "accounts.users_view",
    "accounts.users_change_status": "accounts.users_view",
    "accounts.roles_manage": "accounts.roles_view",
    "producers.create": "producers.view",
    "producers.update": "producers.view",
    "producers.change_status": "producers.view",
    "farms.add_farm": "farms.view_farm",
    "farms.change_farm": "farms.view_farm",
    "farms.delete_farm": "farms.view_farm",
}


def with_dependencies(codes) -> set[str]:
    """Los códigos pedidos más el permiso de vista que cada uno necesita para tener sentido."""
    resolved = set(codes)
    resolved.update(
        dependency
        for code in codes
        if (dependency := PERMISSION_DEPENDENCIES.get(code)) is not None
    )
    return resolved
