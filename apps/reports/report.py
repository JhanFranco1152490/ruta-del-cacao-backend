"""Un reporte ya armado: lo que se ve en pantalla y lo que trae cada archivo exportado.

La pantalla y los tres formatos lo dibujan a partir de `columns`, sin conocer cada tipo de reporte:
así lo que se descarga no puede diferir de lo que se ve. Las filas guardan valores (fechas,
`Decimal`, enteros, texto o `None`); darles formato es de quien los muestra, según el `kind` de su
columna.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

TEXT = "text"
DATE = "date"
KG = "kg"
PCT = "pct"
MONEY = "money"
COUNT = "count"
KINDS = (TEXT, DATE, KG, PCT, MONEY, COUNT)


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str


@dataclass(frozen=True)
class Total:
    key: str
    label: str
    kind: str
    value: Any


@dataclass(frozen=True)
class ReportFilter:
    """Un filtro aplicado, con el texto con que se muestra («F02 · La Esperanza») y, si nombra un
    registro, su id."""

    key: str
    label: str
    text: str
    id: Any = None


@dataclass(frozen=True)
class ReportBody:
    """Lo que arma cada tipo de reporte con sus filas."""

    columns: tuple[Column, ...]
    rows: list[dict]
    totals: tuple[Total, ...]


@dataclass(frozen=True)
class Report:
    type: str
    title: str
    generated_at: datetime
    generated_by: str
    filters: tuple[ReportFilter, ...]
    columns: tuple[Column, ...]
    rows: list[dict] = field(default_factory=list)
    totals: tuple[Total, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.rows
