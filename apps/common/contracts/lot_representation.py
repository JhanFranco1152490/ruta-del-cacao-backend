"""Cómo se nombra un lote fuera de la app de lotes.

Un aviso de poscosecha dice de qué lote habla (su código, su estado, su finca y el cajón o la
marquesina en que está), pero la representación es de la app de lotes y ninguna app importa de
otra (ver AGENTS.md). El punto de encuentro es este módulo: lotes registra en su `ready()` el
serializer reducido de un lote y cómo saber qué precargar desde él, y notificaciones lo usa sin
conocerlo.
"""

from collections.abc import Callable
from typing import Any

_serializer: type | None = None
_prefetch: Callable[[], list[str]] | None = None


def register_lot_brief(serializer: type, prefetch: Callable[[], list[str]]) -> None:
    # La precarga se pide al usarla: incluye lo que fermentación y secado registran, y esas apps
    # pueden arrancar después de la de lotes.
    global _serializer, _prefetch
    _serializer = serializer
    _prefetch = prefetch


def lot_brief_serializer() -> Any:
    if _serializer is None:
        raise RuntimeError("La app de lotes no registró cómo se nombra un lote.")
    return _serializer


def lot_brief_prefetch(relation: str) -> list[str]:
    """Lo que hay que precargar para nombrar el lote al que se llega por `relation`."""
    if _prefetch is None:
        raise RuntimeError("La app de lotes no registró cómo se nombra un lote.")
    return [f"{relation}__{path}" for path in _prefetch()]
