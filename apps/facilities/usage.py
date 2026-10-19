"""Qué registros usan un cajón o una marquesina.

Se recorren las relaciones del modelo en vez de listar las tablas: una tabla nueva que apunte a un
elemento (una fermentación, un secado) cuenta sola desde que existe, y esta app no conoce a las
demás. El historial del propio elemento no cuenta.
"""

from apps.common.db import has_dependent_rows, has_dependent_rows_expression

from .models import PostharvestFacility, PostharvestFacilityAuditEvent

NOT_USAGE = (PostharvestFacilityAuditEvent,)


def is_used(facility: PostharvestFacility) -> bool:
    return has_dependent_rows(facility, ignore=NOT_USAGE)


def used_expression():
    """`has_records` para anotar una consulta."""
    return has_dependent_rows_expression(PostharvestFacility, ignore=NOT_USAGE)
