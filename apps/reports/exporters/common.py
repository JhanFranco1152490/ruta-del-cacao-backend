"""Lo que los tres formatos escriben igual: el encabezado, el nombre del archivo y cómo se protege
una celda de texto."""

import unicodedata
from decimal import Decimal

from django.utils import timezone

from ..report import ASSOCIATION, DATE, KG, MONEY, PCT

# Una hoja de cálculo ejecuta como fórmula el texto que empieza con estos caracteres. Los nombres
# de fincas, compradores o parcelas los escribe el usuario: uno así se escribe con un apóstrofo
# delante para que quede como texto.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(text: str) -> str:
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def report_title(report) -> str:
    if report.audience == ASSOCIATION:
        return f"Reporte de la asociación: {report.title}"
    return f"Reporte de {report.title}"


def header_lines(report) -> list[str]:
    """El tipo de reporte, los filtros aplicados y la fecha de generación, como los muestra la
    pantalla."""
    filters = " · ".join(f"{item.label}: {item.text}" for item in report.filters)
    generated = timezone.localtime(report.generated_at)
    return [
        report_title(report),
        filters or "Sin filtros",
        f"Generado el {generated:%d/%m/%Y} a las {generated:%H:%M} por {report.generated_by}",
    ]


def file_name(report, extension: str) -> str:
    """`reporte-comercializacion-2026-11-12.pdf`: el tipo en minúsculas y sin tildes, y la fecha
    local de generación."""
    slug = _ascii(report.title).lower().replace(" ", "-")
    prefix = "reporte-asociacion" if report.audience == ASSOCIATION else "reporte"
    day = timezone.localtime(report.generated_at).date()
    return f"{prefix}-{slug}-{day.isoformat()}.{extension}"


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def display(value, kind: str) -> str:
    """Un valor como se lee en el PDF: con separador de miles, coma decimal y fecha día primero."""
    if value is None:
        return ""
    if kind in (KG, PCT):
        return _thousands(f"{Decimal(value):,.1f}")
    if kind == MONEY:
        return "$ " + _thousands(f"{value:,}")
    if kind == DATE:
        return value.strftime("%d/%m/%Y")
    if isinstance(value, int):
        return _thousands(f"{value:,}")
    return str(value)


def _thousands(text: str) -> str:
    # Del formato de Python (1,250.5) al colombiano (1.250,5).
    return text.replace(",", "_").replace(".", ",").replace("_", ".")
