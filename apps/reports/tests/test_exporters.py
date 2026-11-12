import csv
import io
import time
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import openpyxl
import pytest
from pypdf import PdfReader

from apps.reports.exceptions import ReportEmpty, ReportTooLarge
from apps.reports.exporters import EXPORTERS, PDF_MAX_ROWS, export
from apps.reports.exporters.common import file_name, header_lines, safe_cell
from apps.reports.report import ASSOCIATION, Column, Report, ReportFilter, Total

BOGOTA = ZoneInfo("America/Bogota")


def sample(**fields):
    defaults = {
        "type": "sales",
        "title": "Comercialización",
        "generated_at": datetime(2026, 11, 12, 10, 15, tzinfo=BOGOTA),
        "generated_by": "Rosa Quintero",
        "filters": (
            ReportFilter("period", "Periodo", "01/01/2026 – 31/03/2026"),
            ReportFilter("farm", "Finca", "F02 · La Esperanza", id="b71e"),
        ),
        "columns": (
            Column("sale_date", "Fecha", "date"),
            Column("buyer", "Comprador", "text"),
            Column("kg", "Kg", "kg"),
            Column("share", "% G1", "pct"),
            Column("subtotal", "Subtotal", "money"),
            Column("lots", "Lotes", "count"),
        ),
        "rows": [
            {
                "sale_date": date(2026, 2, 3),
                "buyer": 'Cacaos "del Norte", S.A.S.',
                "kg": Decimal("1250.5"),
                "share": Decimal("76.3"),
                "subtotal": 2775000,
                "lots": 3,
            },
            {
                "sale_date": date(2026, 2, 4),
                "buyer": '=HYPERLINK("http://x")',
                "kg": Decimal("40.0"),
                "share": None,
                "subtotal": 600000,
                "lots": 1,
            },
        ],
        "totals": (
            Total("sales", "Ventas", "count", 2),
            Total("kg", "Kg", "kg", Decimal("1290.5")),
            Total("total_value", "Valor total", "money", 3375000),
        ),
    }
    return Report(**{**defaults, **fields})


def test_the_header_says_the_type_the_filters_and_when_and_by_whom():
    assert header_lines(sample()) == [
        "Reporte de Comercialización",
        "Periodo: 01/01/2026 – 31/03/2026 · Finca: F02 · La Esperanza",
        "Generado el 12/11/2026 a las 10:15 por Rosa Quintero",
    ]
    assert header_lines(sample(audience=ASSOCIATION, filters=()))[:2] == [
        "Reporte de la asociación: Comercialización",
        "Sin filtros",
    ]


def test_the_file_name_has_the_type_without_accents_and_the_date():
    assert file_name(sample(), "pdf") == "reporte-comercializacion-2026-11-12.pdf"
    assert (
        file_name(sample(type="quality", title="Calidad", audience=ASSOCIATION), "xlsx")
        == "reporte-asociacion-calidad-2026-11-12.xlsx"
    )
    # A las 23:30 en Bogotá ya es el día siguiente en UTC: la fecha es la local.
    late = sample(generated_at=datetime(2026, 11, 12, 23, 30, tzinfo=BOGOTA))
    assert file_name(late, "csv").endswith("2026-11-12.csv")


@pytest.mark.parametrize("text", ["=1+1", "+57 300", "-5", "@SUM(A1)", "\tx", "\rx"])
def test_a_text_that_a_spreadsheet_would_run_is_escaped(text):
    assert safe_cell(text) == "'" + text


def test_a_plain_text_is_left_as_is():
    assert safe_cell("La Esperanza") == "La Esperanza"


def read_csv(report):
    content = export(report, "csv").content
    assert content.startswith("﻿".encode())
    return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))


def test_the_csv_has_the_header_the_table_and_the_totals():
    lines = read_csv(sample())

    assert lines[:3] == [[line] for line in header_lines(sample())]
    assert lines[3] == []
    assert lines[4] == ["Fecha", "Comprador", "Kg", "% G1", "Subtotal", "Lotes"]
    assert lines[5] == [
        "2026-02-03",
        'Cacaos "del Norte", S.A.S.',
        "1250.5",
        "76.3",
        "2775000",
        "3",
    ]
    assert lines[6] == ["2026-02-04", '\'=HYPERLINK("http://x")', "40.0", "", "600000", "1"]
    assert lines[7:] == [
        [],
        ["Totales"],
        ["Ventas", "2"],
        ["Kg", "1290.5"],
        ["Valor total", "3375000"],
    ]


def read_xlsx(report):
    exported = export(report, "xlsx")
    return openpyxl.load_workbook(io.BytesIO(exported.content)).active


def test_the_excel_keeps_the_numbers_as_numbers():
    sheet = read_xlsx(sample())
    values = [[cell.value for cell in row] for row in sheet.iter_rows()]

    assert [row[0] for row in values[:3]] == header_lines(sample())
    assert values[4] == ["Fecha", "Comprador", "Kg", "% G1", "Subtotal", "Lotes"]
    first, second = values[5], values[6]
    assert first[0] == datetime(2026, 2, 3)
    assert first[1] == 'Cacaos "del Norte", S.A.S.'
    assert (first[2], first[3], first[4], first[5]) == (1250.5, 76.3, 2775000, 3)
    assert second[1] == '\'=HYPERLINK("http://x")'
    assert second[3] is None
    assert sheet.cell(row=6, column=3).number_format == "0.0"
    assert sheet.cell(row=6, column=5).number_format == "#,##0"
    assert sheet.auto_filter.ref == "A5:F7"
    totals = [row[:2] for row in values[8:] if row[0]]
    assert totals == [["Totales", None], ["Ventas", 2], ["Kg", 1290.5], ["Valor total", 3375000]]


def pdf_text(report):
    pages = PdfReader(io.BytesIO(export(report, "pdf").content)).pages
    # Un texto largo se parte en varias líneas dentro de su columna.
    return " ".join(" ".join(page.extract_text().split()) for page in pages)


def test_the_pdf_has_the_header_the_rows_and_the_totals():
    text = pdf_text(sample())

    for line in header_lines(sample()):
        assert line in text
    assert "Comprador" in text
    assert 'Cacaos "del Norte", S.A.S.' in text
    assert "1.250,5" in text
    assert "$ 2.775.000" in text
    assert "03/02/2026" in text
    assert "Totales" in text and "$ 3.375.000" in text
    assert "Página 1 de 1" in text


def test_a_long_pdf_numbers_every_page_with_the_total():
    rows = [{**sample().rows[0], "buyer": f"Comprador {index}"} for index in range(200)]
    pages = PdfReader(io.BytesIO(export(sample(rows=rows), "pdf").content)).pages

    assert len(pages) > 2
    assert f"Página {len(pages)} de {len(pages)}" in pages[-1].extract_text()
    assert f"Página 1 de {len(pages)}" in pages[0].extract_text()


def test_each_format_has_its_content_type():
    assert {name: exporter.content_type for name, exporter in EXPORTERS.items()} == {
        "csv": "text/csv; charset=utf-8",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }


def largest_pdf_report(rows: int):
    # Como trazabilidad, el reporte más ancho: 20 columnas, 6 de texto.
    texts = tuple(Column(f"t{index}", f"Texto {index}", "text") for index in range(6))
    numbers = tuple(Column(f"n{index}", f"Cifra {index}", "kg") for index in range(8))
    dates = tuple(Column(f"d{index}", f"Fecha {index}", "date") for index in range(6))
    return sample(
        type="traceability",
        title="Trazabilidad",
        columns=texts + numbers + dates,
        rows=[
            {
                **{column.key: f"F02 · La Esperanza {row}" for column in texts},
                **{column.key: Decimal("1250.5") for column in numbers},
                **{column.key: date(2026, 2, 1) for column in dates},
            }
            for row in range(rows)
        ],
    )


def test_the_widest_pdf_with_the_most_rows_takes_less_than_ten_seconds():
    start = time.perf_counter()
    content = export(largest_pdf_report(PDF_MAX_ROWS), "pdf").content

    assert time.perf_counter() - start < 10
    assert len(PdfReader(io.BytesIO(content)).pages) > 1


def test_a_pdf_over_its_limit_suggests_excel_or_csv():
    report = largest_pdf_report(PDF_MAX_ROWS + 1)

    with pytest.raises(ReportTooLarge) as error:
        export(report, "pdf")

    assert "Excel" in str(error.value.detail)
    assert export(report, "csv").content


@pytest.mark.parametrize("file", ["csv", "xlsx", "pdf"])
def test_an_empty_report_is_not_exported(file):
    with pytest.raises(ReportEmpty) as error:
        export(sample(rows=[]), file)

    assert error.value.status_code == 400
    assert error.value.default_code == "report_empty"
