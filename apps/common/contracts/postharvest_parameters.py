"""Los parámetros de secado vigentes de un productor: los que ajustó a su región o, si no ajustó
nada, la línea base.

El secado los usa para advertir una humedad de entrada fuera de rango y mostrar la meta, y las
alertas de desvío para decidir cuándo avisar. Los guarda otra app y ninguna app importa de otra
(ver AGENTS.md): esa app registra en su `ready()` cómo se leen, y quien los necesita los consulta
aquí sin saber si el productor configuró algo ni dónde se guarda.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class DryingParameters:
    entry_moisture_min_pct: Decimal
    entry_moisture_max_pct: Decimal
    target_moisture_min_pct: Decimal
    target_moisture_max_pct: Decimal
    estimated_days_min: int
    estimated_days_max: int
    slow_stall_window_hours: int
    slow_stall_min_drop_pct: Decimal
    slow_duration_day: int
    slow_duration_moisture_pct: Decimal
    accelerated_day: int
    accelerated_moisture_pct: Decimal
    near_target_min_pct: Decimal
    near_target_max_pct: Decimal
    overdried_moisture_pct: Decimal


_reader: Callable[[Any], DryingParameters] | None = None


def register_drying_parameters(reader: Callable[[Any], DryingParameters]) -> None:
    global _reader
    _reader = reader


def drying_parameters(producer_id: Any) -> DryingParameters:
    """Siempre un juego completo: quien llama nunca decide si usar la línea base. Lee lo vigente
    en ese momento, así que un cambio vale desde la siguiente evaluación, también para los lotes
    que ya están secando. Quien evalúa muchos lotes la llama una vez por productor."""
    if _reader is None:
        raise RuntimeError("La app de parámetros de poscosecha no registró cómo leerlos.")
    return _reader(producer_id)
