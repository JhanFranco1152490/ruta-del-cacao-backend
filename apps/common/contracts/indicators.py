"""Las cifras que cada app aporta a los paneles de indicadores.

Los paneles juntan cosechas, secados, calidad, existencias y ventas, y cada dato lo guarda una app
distinta. Ninguna app importa de otra (ver AGENTS.md): cada dueña registra en su `ready()` una
fuente que devuelve sus cifras ya agregadas, y la app de indicadores las combina sin conocer las
tablas.

Una fuente recibe las fincas como subconsulta de ids, para que sea una sola consulta agregada sin
importar cuántas fincas haya, y devuelve filas de este módulo, nunca modelos ni querysets. Los kg
van como `Decimal`; redondear y calcular proporciones es de quien combina.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

# Los nombres fijos: registrar otro es un error de quien registra, y faltar uno, de configuración.
INDICATOR_SOURCES = frozenset(
    {
        "farm_scope",
        "farms",
        "plots",
        "harvests",
        "drying",
        "quality",
        "warehouse",
        "sales",
    }
)

_sources: dict[str, Callable[..., Any]] = {}


@dataclass(frozen=True)
class IndicatorPeriod:
    """Las fechas locales del periodo, las dos incluidas."""

    date_from: date
    date_to: date

    @staticmethod
    def month_key(day: date) -> str:
        return f"{day.year:04d}-{day.month:02d}"

    def months(self) -> list[str]:
        """Todos los meses que toca el periodo, en orden, también los que no tengan datos."""
        year, month = self.date_from.year, self.date_from.month
        keys = []
        while (year, month) <= (self.date_to.year, self.date_to.month):
            keys.append(f"{year:04d}-{month:02d}")
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return keys


@dataclass(frozen=True)
class ScopedFarm:
    farm_id: Any
    code: str
    name: str
    municipality_code: str
    producer_id: Any
    producer_member_code: str
    producer_first_name: str
    producer_last_name: str
    # Los reportes de la asociación muestran en 0 las fincas activas de productores activos; las
    # demás, solo si tienen cifras.
    is_active: bool = True
    producer_is_active: bool = True


@dataclass(frozen=True)
class PlotArea:
    plot_id: Any
    farm_id: Any
    code: str
    name: str
    area_hectares: Decimal
    is_active: bool


@dataclass(frozen=True)
class PlotMonthKg:
    """Kg en baba que se cosecharon en una parcela en un mes."""

    plot_id: Any
    farm_id: Any
    month: str
    kg: Decimal


@dataclass(frozen=True)
class PlotMonthDried:
    """Lo que dieron los secados terminados de las cosechas de una parcela en un mes (el de la
    cosecha, no el del fin del secado): su peso seco y lo que esas cosechas pesaban en baba, para
    saber cuánto de lo cosechado falta por secar."""

    plot_id: Any
    farm_id: Any
    month: str
    dry_kg: Decimal
    green_kg: Decimal


@dataclass(frozen=True)
class FarmQuality:
    """El descarte incluye el peso seco de los lotes descartados completos."""

    farm_id: Any
    g1_kg: Decimal
    g2_kg: Decimal
    discard_kg: Decimal
    lots_classified: int
    lots_discarded: int


@dataclass(frozen=True)
class FarmGradeKg:
    farm_id: Any
    grade: str
    kg: Decimal


@dataclass(frozen=True)
class FarmMonthSales:
    """Una venta es de una finca y una fecha: contar por finca y mes no repite ninguna al sumar."""

    farm_id: Any
    month: str
    g1_kg: Decimal
    g2_kg: Decimal
    sales: int


def register_indicator_source(name: str, source: Callable[..., Any]) -> None:
    if name not in INDICATOR_SOURCES:
        raise ValueError(f"Fuente de indicadores desconocida: {name}.")
    _sources[name] = source


def indicator_source(name: str) -> Callable[..., Any]:
    try:
        return _sources[name]
    except KeyError:
        raise RuntimeError(f"Ninguna app registró la fuente de indicadores {name}.") from None
