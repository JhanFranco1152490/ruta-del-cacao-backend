"""Lo que otras apps agregan a la representación de una actividad agrícola.

Sanidad guarda el resultado de un monitoreo y la detección que atiende un control, y el calendario
los muestra junto a la actividad. Ninguna app importa de otra (ver AGENTS.md): el punto de
encuentro es este módulo. Sanidad registra en su `ready()` los campos que agrega (cada uno, un
serializer que se lee de la actividad) y lo que hay que precargar para no hacer una consulta por
actividad; actividades los suma a su serializer y a sus consultas sin conocer los modelos.
"""

from collections.abc import Callable
from typing import Any

_fields: dict[str, Callable[[], Any]] = {}
_prefetch: list[str] = []


def register_activity_details(fields: dict[str, Callable[[], Any]], prefetch: list[str]) -> None:
    """`fields` va de nombre a una función que crea el campo (un serializer de solo lectura): se
    crea al armar cada serializer, para que el esquema OpenAPI lo documente con su forma."""
    _fields.update(fields)
    _prefetch.extend(path for path in prefetch if path not in _prefetch)


def activity_detail_fields() -> dict[str, Any]:
    return {name: build() for name, build in _fields.items()}


def activity_detail_prefetch() -> list[str]:
    return list(_prefetch)
