"""Qué depende de un productor y cómo se elimina con él.

Eliminar un productor obliga a eliminar lo que es de otras apps: sus fincas, sus cuentas. Ninguna
app importa de otra (ver AGENTS.md), así que el punto de encuentro es este módulo compartido:
cada app se suma aquí, en su `ready()`, y dice tres cosas de lo suyo: si algo es importante,
cuántos hay y cómo se eliminan. La app de productores lo lee al eliminar uno.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProducerDependent:
    name: str
    # Los otros tres reciben el productor (y, el último, quien actúa): `Any` porque este módulo no
    # importa los modelos de ninguna app.
    # El motivo si hay algo importante que impide eliminar al productor, o None.
    important_record: Callable[[Any], str | None]
    # Cuántos se eliminarían con él.
    count: Callable[[Any], int]
    delete_all: Callable[[Any, Any], None]


_REGISTRY: dict[str, ProducerDependent] = {}


def register_dependent(dependent: ProducerDependent) -> None:
    # Por nombre: volver a cargar un módulo reemplaza el registro en vez de duplicarlo.
    _REGISTRY[dependent.name] = dependent


def registered_dependents() -> list[ProducerDependent]:
    return list(_REGISTRY.values())
