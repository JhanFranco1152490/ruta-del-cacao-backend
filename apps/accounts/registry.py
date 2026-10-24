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
    # Un empleado de confianza que lo tenga solo crea cuentas en la finca en la que trabaja.
    "accounts.users_create": PermissionInfo(area="users", delegable=True),
    "accounts.users_update": PermissionInfo(area="users", delegable=True),
    "accounts.users_change_status": PermissionInfo(area="users", delegable=True),
    "accounts.users_delete": PermissionInfo(area="users", delegable=True),
    "accounts.roles_view": PermissionInfo(area="roles", delegable=True),
    "accounts.roles_manage": PermissionInfo(area="roles", delegable=True),
    # No delegables: administran a todos los productores de la asociación, no el espacio de uno.
    "producers.view": PermissionInfo(area="producers", delegable=False),
    "producers.create": PermissionInfo(area="producers", delegable=False),
    "producers.update": PermissionInfo(area="producers", delegable=False),
    "producers.change_status": PermissionInfo(area="producers", delegable=False),
    "producers.delete": PermissionInfo(area="producers", delegable=False),
    "farms.view_farm": PermissionInfo(area="farms", delegable=True),
    # Un empleado que lo tenga queda asignado a la finca que registra: si no, la perdería de vista.
    "farms.add_farm": PermissionInfo(area="farms", delegable=True),
    "farms.change_farm": PermissionInfo(area="farms", delegable=True),
    "farms.delete_farm": PermissionInfo(area="farms", delegable=True),
    "plots.view_plot": PermissionInfo(area="plots", delegable=True),
    "plots.add_plot": PermissionInfo(area="plots", delegable=True),
    "plots.change_plot": PermissionInfo(area="plots", delegable=True),
    "plots.delete_plot": PermissionInfo(area="plots", delegable=True),
    "crops.change_plotcharacterization": PermissionInfo(area="crops", delegable=True),
    "inputs.view_agriculturalinput": PermissionInfo(area="inputs", delegable=True),
    "inputs.add_agriculturalinput": PermissionInfo(area="inputs", delegable=True),
    "inputs.change_agriculturalinput": PermissionInfo(area="inputs", delegable=True),
    "inputs.delete_agriculturalinput": PermissionInfo(area="inputs", delegable=True),
    "inputs.manage_inputstock": PermissionInfo(area="inputs", delegable=True),
    # No delegable: el catálogo de variedades es común a toda la asociación, no del espacio de
    # un productor.
    "crops.manage_cacaovariety": PermissionInfo(area="crops", delegable=False),
    "activities.view_agriculturalactivity": PermissionInfo(area="activities", delegable=True),
    "activities.add_agriculturalactivity": PermissionInfo(area="activities", delegable=True),
    "activities.change_agriculturalactivity": PermissionInfo(area="activities", delegable=True),
    "activities.complete_agriculturalactivity": PermissionInfo(area="activities", delegable=True),
    "activities.delete_agriculturalactivity": PermissionInfo(area="activities", delegable=True),
    "harvests.view_harvest": PermissionInfo(area="harvests", delegable=True),
    # Quien lo tiene puede ser nombrado recolector de una cosecha.
    "harvests.add_harvest": PermissionInfo(area="harvests", delegable=True),
    "harvests.change_harvest": PermissionInfo(area="harvests", delegable=True),
    "harvests.delete_harvest": PermissionInfo(area="harvests", delegable=True),
    "lots.view_lot": PermissionInfo(area="lots", delegable=True),
    "lots.add_lot": PermissionInfo(area="lots", delegable=True),
    "lots.delete_lot": PermissionInfo(area="lots", delegable=True),
    # No delegable: el catálogo de plagas y enfermedades es común a toda la asociación, como el de
    # variedades.
    "health.manage_pestdisease": PermissionInfo(area="health", delegable=False),
    "facilities.view_postharvestfacility": PermissionInfo(area="facilities", delegable=True),
    "facilities.add_postharvestfacility": PermissionInfo(area="facilities", delegable=True),
    "facilities.change_postharvestfacility": PermissionInfo(area="facilities", delegable=True),
    "facilities.delete_postharvestfacility": PermissionInfo(area="facilities", delegable=True),
    # No son de campo: los parámetros son del productor y valen para todas sus fincas.
    "postharvest_parameters.view_postharvestparameters": PermissionInfo(
        area="postharvest_parameters", delegable=True
    ),
    "postharvest_parameters.change_postharvestparameters": PermissionInfo(
        area="postharvest_parameters", delegable=True
    ),
}


# Las áreas de lo que cuelga de una finca. Un empleado con algún permiso de estas necesita una
# finca asignada: sin ella no alcanza nada de lo que el permiso le deja hacer.
FIELD_AREAS = frozenset(
    {"farms", "plots", "crops", "inputs", "activities", "harvests", "lots", "facilities"}
)


def is_field_permission(code: str) -> bool:
    """Si el permiso es de campo: actúa sobre algo que cuelga de una finca de un productor, y un
    empleado puede tenerlo. Los no delegables de esas áreas no cuentan: son de la asociación (el
    catálogo de variedades), cuyas cuentas no llevan finca."""
    info = PERMISSION_REGISTRY.get(code)
    return info is not None and info.delegable and info.area in FIELD_AREAS


FIELD_PERMISSIONS = frozenset(code for code in PERMISSION_REGISTRY if is_field_permission(code))


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
    "accounts.users_delete": "accounts.users_view",
    "accounts.roles_manage": "accounts.roles_view",
    "producers.create": "producers.view",
    "producers.update": "producers.view",
    "producers.change_status": "producers.view",
    "producers.delete": "producers.view",
    "farms.add_farm": "farms.view_farm",
    "farms.change_farm": "farms.view_farm",
    "farms.delete_farm": "farms.view_farm",
    # Las parcelas se consultan desde su finca: sin ver la finca no hay cómo llegar a ellas.
    "plots.view_plot": "farms.view_farm",
    "plots.add_plot": "plots.view_plot",
    "plots.change_plot": "plots.view_plot",
    "plots.delete_plot": "plots.view_plot",
    # La ficha se registra desde la parcela: sin verla no hay cómo llegar a ella.
    "crops.change_plotcharacterization": "plots.view_plot",
    "inputs.add_agriculturalinput": "inputs.view_agriculturalinput",
    "inputs.change_agriculturalinput": "inputs.view_agriculturalinput",
    "inputs.delete_agriculturalinput": "inputs.view_agriculturalinput",
    "inputs.manage_inputstock": "inputs.view_agriculturalinput",
    # Las actividades se programan y se consultan en una parcela: sin verla no hay cómo llegar a
    # ellas.
    "activities.view_agriculturalactivity": "plots.view_plot",
    "activities.add_agriculturalactivity": "activities.view_agriculturalactivity",
    "activities.change_agriculturalactivity": "activities.view_agriculturalactivity",
    "activities.complete_agriculturalactivity": "activities.view_agriculturalactivity",
    "activities.delete_agriculturalactivity": "activities.view_agriculturalactivity",
    # Las cosechas se registran y se consultan desde una parcela.
    "harvests.view_harvest": "plots.view_plot",
    "harvests.add_harvest": "harvests.view_harvest",
    "harvests.change_harvest": "harvests.view_harvest",
    "harvests.delete_harvest": "harvests.view_harvest",
    # La ficha del lote muestra su origen: sin ver cosechas no hay cómo leerla.
    "lots.view_lot": "harvests.view_harvest",
    "lots.add_lot": "lots.view_lot",
    "lots.delete_lot": "lots.view_lot",
    # Los cajones y marquesinas se consultan eligiendo primero la finca: sin verlas no hay cómo
    # llegar a ellos.
    "facilities.view_postharvestfacility": "farms.view_farm",
    "facilities.add_postharvestfacility": "facilities.view_postharvestfacility",
    "facilities.change_postharvestfacility": "facilities.view_postharvestfacility",
    "facilities.delete_postharvestfacility": "facilities.view_postharvestfacility",
    "postharvest_parameters.change_postharvestparameters": (
        "postharvest_parameters.view_postharvestparameters"
    ),
}


def with_dependencies(codes) -> set[str]:
    """Los códigos pedidos más los permisos de vista que cada uno necesita para tener sentido.

    La dependencia se sigue hasta el final de la cadena: un permiso de vista también puede
    necesitar otro (consultar lo que cuelga de un registro exige poder consultar ese registro).
    """
    resolved = set(codes)
    pending = list(resolved)
    while pending:
        dependency = PERMISSION_DEPENDENCIES.get(pending.pop())
        if dependency is not None and dependency not in resolved:
            resolved.add(dependency)
            pending.append(dependency)
    return resolved
