"""Qué registros usan un insumo.

Se recorren las relaciones del modelo en vez de listar las tablas: una tabla nueva (actividades,
controles) que apunte a un insumo cuenta sola desde que existe, y esta app no conoce a las demás.
El historial del propio insumo no cuenta, y sus existencias tampoco: la fila de existencias dice
en qué finca está el insumo, y existe desde que alguien lo registra allí. Lo que lo vuelve usado
son sus movimientos.
"""

from apps.common.db import has_dependent_rows, has_dependent_rows_expression

from .models import AgriculturalInput, AgriculturalInputAuditEvent, InputStock

NOT_USAGE = (AgriculturalInputAuditEvent, InputStock)


def is_used(item: AgriculturalInput) -> bool:
    return has_dependent_rows(item, ignore=NOT_USAGE)


def used_expression():
    """`has_records` para anotar una consulta."""
    return has_dependent_rows_expression(AgriculturalInput, ignore=NOT_USAGE)
