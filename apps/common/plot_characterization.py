"""Si una parcela tiene ficha agronómica.

La lista de parcelas filtra y cuenta por eso, pero la ficha es de otra app y ninguna app importa
de otra (ver AGENTS.md). El punto de encuentro es este módulo: la app de fichas registra en su
`ready()` cómo se sabe si una parcela tiene ficha, y la de parcelas lo usa sin conocer el modelo.
"""

from collections.abc import Callable
from typing import Any

# Recibe la referencia al id de la parcela en la consulta de afuera (un `OuterRef`) y devuelve una
# expresión booleana (un `Exists`). `Any`: este módulo no importa expresiones de ninguna app.
_characterized: Callable[[Any], Any] | None = None


def register_characterized(expression: Callable[[Any], Any]) -> None:
    global _characterized
    _characterized = expression


def characterized(plot_ref: Any) -> Any:
    if _characterized is None:
        raise RuntimeError("La app de fichas no registró cómo saber si una parcela tiene ficha.")
    return _characterized(plot_ref)
