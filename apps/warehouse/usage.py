"""Qué registros usan una bodega.

Se recorren las relaciones del modelo en vez de listar las tablas: una tabla nueva que apunte a una
bodega cuenta sola desde que existe. El historial de la propia bodega no cuenta.
"""

from apps.common.db import has_dependent_rows, has_dependent_rows_expression

from .models import Warehouse, WarehouseAuditEvent

NOT_USAGE = (WarehouseAuditEvent,)


def is_used(warehouse: Warehouse) -> bool:
    return has_dependent_rows(warehouse, ignore=NOT_USAGE)


def used_expression():
    """`in_use` para anotar una consulta."""
    return has_dependent_rows_expression(Warehouse, ignore=NOT_USAGE)
