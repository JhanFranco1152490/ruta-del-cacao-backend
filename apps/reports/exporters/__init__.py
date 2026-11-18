"""Un reporte como archivo. Cada formato solo conoce `Report`, nunca el tipo de reporte: el archivo
trae siempre lo mismo que la pantalla."""

from collections.abc import Callable
from dataclasses import dataclass

from ..exceptions import ReportEmpty, ReportTooLarge
from . import csv, pdf, xlsx
from .common import file_name

# Un PDF de más filas pasa de cien páginas: nadie lo lee y tarda en armarse. Para eso están el
# Excel y el CSV, que no tienen más límite que el del reporte.
PDF_MAX_ROWS = 2000


@dataclass(frozen=True)
class Exporter:
    content_type: str
    extension: str
    write: Callable
    max_rows: int | None = None


@dataclass(frozen=True)
class ExportedFile:
    content: bytes
    content_type: str
    file_name: str


EXPORTERS = {
    "csv": Exporter("text/csv; charset=utf-8", "csv", csv.write),
    "xlsx": Exporter(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx", xlsx.write
    ),
    "pdf": Exporter("application/pdf", "pdf", pdf.write, max_rows=PDF_MAX_ROWS),
}


def export(report, file: str) -> ExportedFile:
    exporter = EXPORTERS[file]
    if report.is_empty:
        raise ReportEmpty()
    if exporter.max_rows is not None and len(report.rows) > exporter.max_rows:
        raise ReportTooLarge(
            f"El PDF admite hasta {exporter.max_rows} filas. Acota los filtros o exporta a Excel "
            "o CSV."
        )
    return ExportedFile(
        content=exporter.write(report),
        content_type=exporter.content_type,
        file_name=file_name(report, exporter.extension),
    )
