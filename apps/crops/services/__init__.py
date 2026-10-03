"""Servicios del dominio de cultivos: catálogo de variedades y caracterización de parcelas."""

from .varieties import create_variety, delete_variety, list_varieties, name_taken, update_variety

__all__ = ["create_variety", "delete_variety", "list_varieties", "name_taken", "update_variety"]
