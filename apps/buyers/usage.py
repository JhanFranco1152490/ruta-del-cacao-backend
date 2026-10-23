"""Qué registros usan un comprador.

Se recorren las relaciones del modelo en vez de listar las tablas: una tabla nueva (las ventas) que
apunte a un comprador cuenta sola desde que existe, y esta app no conoce a las demás. El historial
del propio comprador no cuenta.
"""

from apps.common.db import has_dependent_rows, has_dependent_rows_expression

from .models import Buyer, BuyerAuditEvent

NOT_USAGE = (BuyerAuditEvent,)


def is_used(buyer: Buyer) -> bool:
    return has_dependent_rows(buyer, ignore=NOT_USAGE)


def used_expression():
    """`has_records` para anotar una consulta."""
    return has_dependent_rows_expression(Buyer, ignore=NOT_USAGE)
