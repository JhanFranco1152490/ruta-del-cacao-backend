"""El reporte en CSV: para llevar los datos a otro programa, así que los números van sin formato
(punto decimal, sin separador de miles) y las fechas en ISO."""

import csv
import io

from ..report import DATE, KG, PCT
from .common import header_lines, safe_cell

# UTF-8 con BOM: sin él, Excel en Windows lee mal las tildes.
ENCODING = "utf-8-sig"


def write(report) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for line in header_lines(report):
        writer.writerow([safe_cell(line)])
    writer.writerow([])
    writer.writerow([column.label for column in report.columns])
    for row in report.rows:
        writer.writerow([_value(row[column.key], column.kind) for column in report.columns])
    writer.writerow([])
    writer.writerow(["Totales"])
    for total in report.totals:
        writer.writerow([total.label, _value(total.value, total.kind)])
    return buffer.getvalue().encode(ENCODING)


def _value(value, kind: str) -> str:
    if value is None:
        return ""
    if kind in (KG, PCT):
        return f"{value:.1f}"
    if kind == DATE:
        return value.isoformat()
    if isinstance(value, str):
        return safe_cell(value)
    return str(value)
