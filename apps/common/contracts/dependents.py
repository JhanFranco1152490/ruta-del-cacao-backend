"""Registro de lo que depende de un registro y se elimina con él.

Eliminar un productor obliga a eliminar lo que es de otras apps (fincas, cuentas), y eliminar una
finca, sus parcelas. Ninguna app importa de otra (ver AGENTS.md), así que el punto de encuentro
es este módulo compartido: cada app se suma a un registro en su `ready()` y dice tres cosas de lo
suyo: si algo es importante, cuántos hay y cómo se eliminan. Quien elimina el registro padre lee
el registro.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Dependent:
    name: str
    # Los otros tres reciben el registro padre (y, el último, quien actúa): `Any` porque este
    # módulo no importa los modelos de ninguna app.
    # El motivo si hay algo importante que impide eliminar al padre, o None.
    important_record: Callable[[Any], str | None]
    # Cuántos se eliminarían con él.
    count: Callable[[Any], int]
    delete_all: Callable[[Any, Any], None]
    # Los modelos que `delete_all` elimina por su cuenta: quien revisa si el padre tiene otras
    # tablas apuntándole no los cuenta como desconocidos.
    models: tuple[type, ...] = ()


class DependentRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Dependent] = {}

    def register(self, dependent: Dependent) -> None:
        # Por nombre: volver a cargar un módulo reemplaza el registro en vez de duplicarlo.
        self._items[dependent.name] = dependent

    def all(self) -> list[Dependent]:
        return list(self._items.values())
