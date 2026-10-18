"""Cuántos árboles tiene una parcela según su ficha agronómica.

El monitoreo de sanidad no puede evaluar más árboles de los que tiene la parcela, pero la ficha es
de otra app y ninguna app importa de otra (ver AGENTS.md). El punto de encuentro es este módulo: la
app de fichas registra en su `ready()` cómo se cuentan los árboles y la de sanidad lo consulta sin
conocer el modelo.
"""

from collections.abc import Callable
from typing import Any

_tree_count: Callable[[Any], int | None] | None = None


def register_tree_count(counter: Callable[[Any], int | None]) -> None:
    global _tree_count
    _tree_count = counter


def tree_count(plot_id: Any) -> int | None:
    """Los árboles de la parcela, o `None` si su ficha todavía no dice cuántos."""
    if _tree_count is None:
        raise RuntimeError("La app de fichas no registró cómo contar los árboles de una parcela.")
    return _tree_count(plot_id)
