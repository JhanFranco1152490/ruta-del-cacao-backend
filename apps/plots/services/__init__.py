"""Servicios del dominio de parcelas."""

from .create import create_plot
from .queries import get_plot, list_plots
from .update import update_plot

__all__ = ["create_plot", "get_plot", "list_plots", "update_plot"]
