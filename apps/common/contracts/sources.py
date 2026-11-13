"""Un registro de fuentes con nombre fijo, para los contratos en los que cada app dueña de un dato
aporta una función y otra app las combina sin importarlas."""

from collections.abc import Callable, Iterable
from typing import Any


class SourceRegistry:
    def __init__(self, kind: str, names: Iterable[str]):
        self.kind = kind
        self.names = frozenset(names)
        self._sources: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, source: Callable[..., Any]) -> None:
        # Registrar otro nombre es un error de quien registra; que falte uno, de configuración.
        if name not in self.names:
            raise ValueError(f"Fuente {self.kind} desconocida: {name}.")
        self._sources[name] = source

    def get(self, name: str) -> Callable[..., Any]:
        try:
            return self._sources[name]
        except KeyError:
            raise RuntimeError(f"Ninguna app registró la fuente {self.kind} {name}.") from None
