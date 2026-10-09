"""Servicios del catálogo de insumos y de su inventario."""

from .create import create_input
from .delete import delete_input, remove_input
from .inventory_queries import get_stock, list_movements, list_stocks
from .movements import record_consumption, register_movement
from .queries import get_input, list_inputs
from .update import update_input

__all__ = [
    "create_input",
    "delete_input",
    "get_input",
    "get_stock",
    "list_inputs",
    "list_movements",
    "list_stocks",
    "record_consumption",
    "register_movement",
    "remove_input",
    "update_input",
]
