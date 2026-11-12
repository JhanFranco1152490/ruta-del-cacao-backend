import csv
import io
from datetime import date

import openpyxl
import pytest
from django.utils import timezone
from pypdf import PdfReader

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator

from .helpers import PERIOD, Estate, generate, harvest

pytestmark = pytest.mark.django_db

PRODUCER_URL = "/api/reports/producer/export"
ASSOCIATION_URL = "/api/reports/association/export"


@pytest.fixture
def estate():
    estate = Estate()
    harvest(estate.rio, date(2026, 2, 3), "120.5")
    harvest(estate.alto, date(2026, 2, 4), "30.0")
    return estate


def download(client, url, **query):
    response = client.get(url, query)
    assert response.status_code == 200, response.content
    return response


def test_the_csv_brings_the_same_rows_and_totals_as_the_screen(auth_client, estate):
    query = {"type": "production", **PERIOD}
    screen = auth_client(estate.owner).get("/api/reports/producer", query).json()

    response = download(auth_client(estate.owner), PRODUCER_URL, file="csv", **query)

    assert response["Content-Type"] == "text/csv; charset=utf-8"
    today = timezone.localdate().isoformat()
    assert response["Content-Disposition"] == (
        f'attachment; filename="reporte-produccion-{today}.csv"'
    )
    assert "no-store" in response["Cache-Control"]
    assert response["X-Content-Type-Options"] == "nosniff"
    lines = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert lines[0] == ["Reporte de Producción"]
    assert lines[1] == ["Periodo: 01/01/2026 – 31/03/2026"]
    assert lines[2][0].startswith("Generado el ")
    assert lines[4] == [column["label"] for column in screen["columns"]]
    table = lines[5 : 5 + len(screen["rows"])]
    assert [line[5] for line in table] == [row["green_kg"] for row in screen["rows"]]
    totals = lines[5 + len(screen["rows"]) + 2 :]
    assert totals == [[total["label"], str(total["value"])] for total in screen["totals"]]


def test_the_excel_and_the_pdf_download_with_their_type(auth_client, estate):
    query = {"type": "production", **PERIOD}

    excel = download(auth_client(estate.owner), PRODUCER_URL, file="xlsx", **query)
    pdf = download(auth_client(estate.owner), PRODUCER_URL, file="pdf", **query)

    sheet = openpyxl.load_workbook(io.BytesIO(excel.content)).active
    assert sheet["A1"].value == "Reporte de Producción"
    assert sheet.cell(row=6, column=6).value == 120.5
    assert pdf["Content-Type"] == "application/pdf"
    text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    assert "Reporte de Producción" in text and "120,5" in text


def test_the_association_file_is_named_after_the_association(auth_client, estate):
    response = download(
        auth_client(make_administrator()),
        ASSOCIATION_URL,
        file="csv",
        type="production",
        **PERIOD,
    )

    assert 'filename="reporte-asociacion-produccion-' in response["Content-Disposition"]


def test_a_report_without_results_is_not_exported(auth_client, estate):
    response = auth_client(estate.owner).get(
        PRODUCER_URL, {"type": "quality", "file": "pdf", **PERIOD}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "report_empty"


def test_the_file_format_is_required_and_known(auth_client, estate):
    missing = auth_client(estate.owner).get(PRODUCER_URL, {"type": "production", **PERIOD})
    unknown = auth_client(estate.owner).get(
        PRODUCER_URL, {"type": "production", "file": "docx", **PERIOD}
    )

    assert missing.status_code == unknown.status_code == 400
    assert set(missing.json()["fields"]) == {"file"}
    assert set(unknown.json()["fields"]) == {"file"}


def test_the_errors_come_as_json_and_not_as_a_file(auth_client, estate):
    response = auth_client(estate.owner).get(
        PRODUCER_URL,
        {"file": "pdf", "type": "production", "from": "2026-03-01", "to": "2026-01-01"},
    )

    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/json")


def test_exporting_asks_for_the_same_permissions_as_generating(auth_client, estate):
    without_module = estate.employee(farm=estate.esperanza)

    producer_at_association = auth_client(estate.owner).get(
        ASSOCIATION_URL, {"type": "production", "file": "csv", **PERIOD}
    )
    employee = auth_client(without_module).get(
        PRODUCER_URL, {"type": "production", "file": "csv", **PERIOD}
    )

    assert producer_at_association.status_code == 403
    assert employee.status_code == 403


def test_a_name_that_looks_like_a_formula_is_escaped_in_the_csv(auth_client, estate):
    collector = UserFactory(producer=estate.producer, first_name="=CMD()", last_name="")
    harvest(estate.loma, date(2026, 2, 5), "1.0", collector=collector)

    response = download(
        auth_client(estate.owner), PRODUCER_URL, file="csv", type="production", **PERIOD
    )

    assert ",'=CMD()," in response.content.decode("utf-8-sig")
    rows = generate(estate.owner, type="production", **PERIOD).rows
    assert "=CMD()" in [row["collector"] for row in rows]
