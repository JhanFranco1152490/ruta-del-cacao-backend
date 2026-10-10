"""Qué registros usan un insumo.

Se recorren las relaciones del modelo en vez de listar las tablas: una tabla nueva (actividades,
controles) que apunte a un insumo cuenta sola desde que existe, y esta app no conoce a las demás.
El historial del propio insumo no cuenta.
"""

from functools import reduce
from operator import or_

from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Value

from apps.common.db import dependent_relations, has_dependent_rows

from .models import AgriculturalInput, AgriculturalInputAuditEvent


def usage_relations():
    return dependent_relations(AgriculturalInput, ignore=(AgriculturalInputAuditEvent,))


def is_used(item: AgriculturalInput) -> bool:
    return has_dependent_rows(item, ignore=(AgriculturalInputAuditEvent,))


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
