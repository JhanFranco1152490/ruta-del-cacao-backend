from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionInfo:
    area: str
    delegable: bool


# Todo permiso que el catálogo de `/api/permissions` expone (y arma los roles del sistema en
# `system_roles.py`) se declara aquí, con el área que agrupa su catálogo en el frontend y si un
# productor puede delegarlo en sus roles propios. Un código ausente es no delegable por
# defecto: la salvaguarda de HU-03 falla cerrado ante un permiso nuevo que nadie clasificó
# todavía, aunque en la práctica todo permiso real del sistema debería estar aquí.
PERMISSION_REGISTRY: dict[str, PermissionInfo] = {
    "accounts.users_view": PermissionInfo(area="users", delegable=True),
    "accounts.users_create": PermissionInfo(area="users", delegable=True),
    "accounts.users_update": PermissionInfo(area="users", delegable=True),
    "accounts.users_change_status": PermissionInfo(area="users", delegable=True),
    "accounts.roles_view": PermissionInfo(area="roles", delegable=True),
    "accounts.roles_manage": PermissionInfo(area="roles", delegable=True),
    "accounts.association_access_manage": PermissionInfo(
        area="association_access", delegable=False
    ),
    "producers.view": PermissionInfo(area="producers", delegable=False),
    "producers.create": PermissionInfo(area="producers", delegable=False),
    "producers.update": PermissionInfo(area="producers", delegable=False),
    "producers.change_status": PermissionInfo(area="producers", delegable=False),
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
