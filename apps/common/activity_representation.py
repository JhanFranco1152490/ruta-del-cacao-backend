"""Cómo se entrega una actividad agrícola en la API.

Sanidad responde con la actividad completa al registrar un monitoreo o crear un control, pero la
representación es de la app de actividades y ninguna app importa de otra (ver AGENTS.md). El punto
de encuentro es este módulo: actividades registra en su `ready()` el serializer de una actividad, y
sanidad lo usa para responder y para documentar el esquema sin conocerlo.
"""

from typing import Any

_serializer: type | None = None


def register_activity_serializer(serializer: type) -> None:
    global _serializer
    _serializer = serializer


def activity_serializer() -> Any:
    if _serializer is None:
        raise RuntimeError("La app de actividades no registró cómo se representa una actividad.")
    return _serializer
