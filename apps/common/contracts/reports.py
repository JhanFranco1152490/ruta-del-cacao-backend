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
from typing import Any

from .sources import SourceRegistry

REPORT_SOURCES = frozenset({"plot_in_scope", "lot_in_scope"})

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


def register_report_source(name: str, source: Callable[..., Any]) -> None:
    _registry.register(name, source)


def report_source(name: str) -> Callable[..., Any]:
    return _registry.get(name)
