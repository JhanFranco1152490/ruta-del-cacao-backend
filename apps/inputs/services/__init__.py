"""Servicios del catálogo de insumos."""

from .create import create_input
from .delete import delete_input, remove_input
from .queries import get_input, list_inputs
from .update import update_input

__all__ = [
    "create_input",
    "delete_input",
    "get_input",
    "list_inputs",
    "remove_input",
    "update_input",
]
