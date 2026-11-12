"""Las filas que cada app aporta a los reportes del productor.

Un reporte lista cosechas, lotes, clasificaciones, existencias o ventas uno por uno, y cada dato lo
guarda una app distinta. Ninguna app importa de otra (ver AGENTS.md): cada dueña registra en su
`ready()` una fuente que devuelve filas de este módulo, nunca modelos ni querysets, y la app de
reportes las combina sin conocer las tablas. Las fincas del alcance llegan como subconsulta de ids
(la fuente `farm_scope` de los indicadores), así que cada fuente es una sola consulta.

Los reportes de la asociación no usan este módulo: son las cifras por finca de los indicadores.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from apps.common.codes import format_code

from .sources import SourceRegistry

REPORT_SOURCES = frozenset(
    {
        "plot_in_scope",
        "lot_in_scope",
        "harvest_rows",
        "lot_rows",
        "fermentation_dates",
        "drying_results",
    }
)

_registry = SourceRegistry("de reportes", REPORT_SOURCES)


@dataclass(frozen=True)
class ScopedPlot:
    plot_id: Any
    farm_id: Any
    code: str
    name: str


@dataclass(frozen=True)
class ScopedLot:
    lot_id: Any
    farm_id: Any
    plot_id: Any
    code: str


@dataclass(frozen=True)
class PlotPlace:
    """Dónde está algo: su finca y su parcela, con los códigos y los nombres con que se muestran.
    Una parcela sin nombre lo tiene vacío."""

    farm_id: Any
    farm_code: str
    farm_name: str
    plot_id: Any
    plot_code: str
    plot_name: str

    @classmethod
    def of(cls, plot) -> "PlotPlace":
        """De una parcela con su finca ya cargada (`select_related`)."""
        return cls(
            farm_id=plot.farm_id,
            farm_code=format_code("F", plot.farm.number),
            farm_name=plot.farm.name,
            plot_id=plot.pk,
            plot_code=format_code("P", plot.number),
            plot_name=plot.name or "",
        )


@dataclass(frozen=True)
class HarvestRow:
    """Una cosecha y, si forma un lote, el lote. El recolector, la variedad y el estado del lote
    vienen como se muestran."""

    harvest_id: Any
    harvest_date: date
    place: PlotPlace
    variety: str
    collector: str
    green_kg: Decimal
    lot_id: Any | None
    lot_code: str | None
    lot_status: str | None


@dataclass(frozen=True)
class LotRow:
    """Un lote con la cosecha que lo formó. El estado viene como se muestra."""

    lot_id: Any
    code: str
    status: str
    harvest_date: date
    place: PlotPlace
    green_kg: Decimal


@dataclass(frozen=True)
class FermentationDates:
    """Las fechas locales de la fermentación de un lote; sin terminar, sin fin."""

    lot_id: Any
    started_on: date
    ended_on: date | None


@dataclass(frozen=True)
class DryingResult:
    """Lo que dio el secado terminado de un lote, con su fecha local de fin."""

    lot_id: Any
    ended_on: date
    dry_kg: Decimal
    yield_pct: Decimal


def register_report_source(name: str, source: Callable[..., Any]) -> None:
    _registry.register(name, source)


def report_source(name: str) -> Callable[..., Any]:
    return _registry.get(name)
