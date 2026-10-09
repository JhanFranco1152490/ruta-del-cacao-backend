"""Servicios del dominio de parcelas."""

from .create import create_plot
from .delete import delete_plot
from .queries import count_characterizations, get_plot, list_plots, with_characterization
from .update import update_plot

__all__ = [
    "count_characterizations",
    "create_plot",
    "delete_plot",
    "get_plot",
    "list_plots",
    "update_plot",
    "with_characterization",
]
