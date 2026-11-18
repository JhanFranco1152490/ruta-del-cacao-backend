"""Las etapas que cada app aporta a la historia de un lote.

La historia de un lote junta lo que guardan varias apps: la fermentación, el secado, la calidad,
la bodega y las ventas. Ninguna app importa de otra (ver AGENTS.md): cada dueña registra en su
`ready()` una fuente que recibe el lote y devuelve sus etapas como `LotHistoryStage`, nunca modelos
ni querysets, y el serializer de los datos de su tipo de etapa. La app de lotes las junta, las
ordena y las serializa sin conocer las tablas.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone

from .sources import SourceRegistry

# Los tipos de etapa en el orden del proceso. Dos etapas del mismo día se ordenan por aquí.
STAGE_KINDS = (
    "harvest",
    "lot_created",
    "fermentation",
    "drying",
    "evaluation",
    "classification",
    "discard",
    "stock_entry",
    "stock_move",
    "stock_exit",
    "sale",
)

LOT_HISTORY_SOURCES = frozenset(
    {
        "fermentation_history",
        "drying_history",
        "quality_history",
        "warehouse_history",
        "stock_now",
        "sales_history",
        "sold_now",
    }
)

_sources = SourceRegistry("de la historia del lote", LOT_HISTORY_SOURCES)
_serializers: dict[str, Callable[[], Any]] = {}


def _check_kind(kind: str) -> None:
    if kind not in STAGE_KINDS:
        raise ValueError(f"Tipo de etapa desconocido: {kind}.")


@dataclass(frozen=True)
class LotHistoryStage:
    """Una etapa de la historia. `occurred_on` es la fecha local en que empieza; `occurred_at`, su
    hora, si la tiene (una venta o un ingreso a bodega solo tienen fecha). `recorded_at` es cuándo
    se registró, para desempatar dos etapas sin hora del mismo día. `data` es lo propio de cada
    tipo, que serializa el serializer que la app registró para ese tipo."""

    kind: str
    occurred_on: date
    occurred_at: datetime | None
    recorded_at: datetime
    data: Any

    def __post_init__(self):
        _check_kind(self.kind)

    @classmethod
    def at(cls, kind: str, occurred_at: datetime, *, recorded_at: datetime, data: Any):
        """Una etapa con hora: su fecha es la local, no la de UTC."""
        return cls(kind, timezone.localdate(occurred_at), occurred_at, recorded_at, data)

    @classmethod
    def on(cls, kind: str, occurred_on: date, *, recorded_at: datetime, data: Any):
        """Una etapa que solo tiene fecha."""
        return cls(kind, occurred_on, None, recorded_at, data)


@dataclass(frozen=True)
class LotStock:
    """Lo que le queda hoy en bodega a un lote que ingresó. Un calibre agotado, o que no ingresó,
    tiene 0."""

    g1_available_kg: Decimal
    g2_available_kg: Decimal


@dataclass(frozen=True)
class LotSold:
    """Lo vendido de un lote, sin las ventas anuladas."""

    sold_kg: Decimal


def register_lot_history_source(name: str, source: Callable[..., Any]) -> None:
    _sources.register(name, source)


def lot_history_source(name: str) -> Callable[..., Any]:
    return _sources.get(name)


def register_stage_serializer(kind: str, factory: Callable[[], Any]) -> None:
    """`factory` crea el serializer de los datos de `kind`: se crea al armar cada respuesta, para
    que el esquema OpenAPI lo documente con su forma."""
    _check_kind(kind)
    _serializers[kind] = factory


def stage_serializers() -> dict[str, Any]:
    return {kind: factory() for kind, factory in _serializers.items()}
