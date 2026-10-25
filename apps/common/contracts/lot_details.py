"""Lo que otras apps agregan a la representación de un lote.

Fermentación y secado guardan cada uno su etapa del lote, y la lista y la ficha de lotes la
muestran (el cajón de un lote en fermentación, el rendimiento de uno seco). Ninguna app importa de
otra (ver AGENTS.md): el punto de encuentro es este módulo. Cada app registra en su `ready()` los
campos que agrega (cada uno, un serializer que se lee del lote) y lo que hay que precargar para no
hacer una consulta por lote; lotes los suma a su serializer y a sus consultas sin conocer los
modelos.
"""

from collections.abc import Callable
from typing import Any

_fields: dict[str, Callable[[], Any]] = {}
_prefetch: list[str] = []


def register_lot_details(fields: dict[str, Callable[[], Any]], prefetch: list[str]) -> None:
    """`fields` va de nombre a una función que crea el campo (un serializer de solo lectura): se
    crea al armar cada serializer, para que el esquema OpenAPI lo documente con su forma."""
    _fields.update(fields)
    _prefetch.extend(path for path in prefetch if path not in _prefetch)


def lot_detail_fields() -> dict[str, Any]:
    return {name: build() for name, build in _fields.items()}


def lot_detail_prefetch() -> list[str]:
    return list(_prefetch)
