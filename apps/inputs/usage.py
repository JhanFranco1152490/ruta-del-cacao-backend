"""Qué registros usan un insumo.

Se recorren las relaciones del modelo en vez de listar las tablas: una tabla nueva (actividades,
controles) que apunte a un insumo cuenta sola desde que existe, y esta app no conoce a las demás.
El historial del propio insumo no cuenta, y sus existencias tampoco: la fila de existencias dice
en qué finca está el insumo, y existe desde que alguien lo registra allí. Lo que lo vuelve usado
son sus movimientos.
"""

from functools import reduce
from operator import or_

from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Value

from apps.common.db import dependent_relations, has_dependent_rows

from .models import AgriculturalInput, AgriculturalInputAuditEvent, InputStock

NOT_USAGE = (AgriculturalInputAuditEvent, InputStock)


def usage_relations():
    return dependent_relations(AgriculturalInput, ignore=NOT_USAGE)


def is_used(item: AgriculturalInput) -> bool:
    return has_dependent_rows(item, ignore=NOT_USAGE)


def used_expression():
    """`has_records` para anotar una consulta: un `Exists` por tabla, sin una consulta por fila."""
    exists = [
        Exists(
            relation.related_model._base_manager.filter(**{relation.field.name: OuterRef("pk")})
        )
        for relation in usage_relations()
    ]
    if not exists:
        return Value(False, output_field=BooleanField())
    return ExpressionWrapper(reduce(or_, exists), output_field=BooleanField())
