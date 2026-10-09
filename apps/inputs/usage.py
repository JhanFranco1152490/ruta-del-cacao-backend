"""Qué registros usan un insumo.

Se recorren las relaciones del modelo en vez de listar las tablas: una tabla nueva (actividades,
controles) que apunte a un insumo cuenta sola desde que existe, y esta app no conoce a las demás.
El historial del propio insumo no cuenta.
"""

from functools import reduce
from operator import or_

from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef, Value

from .models import AgriculturalInput, AgriculturalInputAuditEvent


def usage_relations():
    # Con `include_hidden`: una tabla que apunte al insumo sin nombre inverso (`related_name="+"`)
    # también lo usa.
    return [
        relation
        for relation in AgriculturalInput._meta.get_fields(include_hidden=True)
        if relation.auto_created
        and not relation.concrete
        and relation.related_model is not AgriculturalInputAuditEvent
    ]


def is_used(item: AgriculturalInput) -> bool:
    return any(
        relation.related_model._base_manager.filter(**{relation.field.name: item}).exists()
        for relation in usage_relations()
    )


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
