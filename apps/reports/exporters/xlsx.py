"""El reporte en Excel: una hoja con el encabezado, la tabla con filtro automático y los totales.
Los kg, porcentajes, pesos y conteos van como números, para poder sumarlos y ordenarlos."""

import io
from datetime import datetime, time

import xlsxwriter

from ..report import COUNT, DATE, KG, MONEY, PCT
from .common import header_lines, safe_cell

NUMBER_FORMATS = {KG: "0.0", PCT: "0.0", MONEY: "#,##0", COUNT: "0", DATE: "dd/mm/yyyy"}
# Excel no acepta más de 31 caracteres en el nombre de una hoja.
SHEET_NAME_LENGTH = 31
MAX_COLUMN_WIDTH = 40


def write(report) -> bytes:
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    sheet = workbook.add_worksheet(report.title[:SHEET_NAME_LENGTH])
    bold = workbook.add_format({"bold": True})
    formats = {
        kind: workbook.add_format({"num_format": code}) for kind, code in NUMBER_FORMATS.items()
    }

    for index, line in enumerate(header_lines(report)):
        sheet.write_string(index, 0, safe_cell(line), bold if index == 0 else None)
    header_row = len(header_lines(report)) + 1
    widths = [len(column.label) for column in report.columns]
    for col, column in enumerate(report.columns):
        sheet.write_string(header_row, col, column.label, bold)
    for offset, row in enumerate(report.rows, start=1):
        for col, column in enumerate(report.columns):
            value = row[column.key]
            _write(sheet, header_row + offset, col, value, column.kind, formats)
            widths[col] = max(widths[col], len(str(value or "")))
    last_row = header_row + len(report.rows)
    sheet.autofilter(header_row, 0, last_row, len(report.columns) - 1)
    for col, width in enumerate(widths):
        sheet.set_column(col, col, min(width + 2, MAX_COLUMN_WIDTH))

    totals_row = last_row + 2
    sheet.write_string(totals_row, 0, "Totales", bold)
    for offset, total in enumerate(report.totals, start=1):
        sheet.write_string(totals_row + offset, 0, total.label)
        _write(sheet, totals_row + offset, 1, total.value, total.kind, formats)
    workbook.close()
    return buffer.getvalue()


def _write(sheet, row: int, col: int, value, kind: str, formats: dict) -> None:
    if value is None:
        sheet.write_blank(row, col, None)
    elif kind == DATE:
        sheet.write_datetime(row, col, datetime.combine(value, time.min), formats[DATE])
    elif kind in formats:
        sheet.write_number(row, col, float(value), formats[kind])
    else:
        sheet.write_string(row, col, safe_cell(str(value)))
