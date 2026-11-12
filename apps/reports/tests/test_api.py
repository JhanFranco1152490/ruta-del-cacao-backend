from datetime import date

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_delegate
from apps.buyers.tests.factories import BuyerFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.sales.tests.helpers import sale_with_lines

from .helpers import PERIOD, Estate, dry, harvest

pytestmark = pytest.mark.django_db

PRODUCER_URL = "/api/reports/producer"
ASSOCIATION_URL = "/api/reports/association"


@pytest.fixture
def estate():
    return Estate()


def test_the_producer_report_comes_with_its_cells_as_text_or_numbers(auth_client, estate):
    dry(LotFactory(harvest=harvest(estate.rio, date(2026, 2, 3), "120.5")), "40.5", "33.6")
    harvest(estate.loma, date(2026, 2, 4), "10.0")

    response = auth_client(estate.owner).get(
        PRODUCER_URL, {"type": "production", **PERIOD, "farm": str(estate.esperanza.pk)}
    )

    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    body = response.json()
    assert (body["type"], body["title"]) == ("production", "Producción")
    assert body["filters"] == [
        {"key": "period", "label": "Periodo", "text": "01/01/2026 – 31/03/2026", "id": None},
        {
            "key": "farm",
            "label": "Finca",
            "text": "F01 · La Esperanza",
            "id": str(estate.esperanza.pk),
        },
    ]
    assert body["columns"][0] == {"key": "harvest_date", "label": "Fecha", "kind": "date"}
    first, second = body["rows"]
    assert (first["harvest_date"], first["green_kg"], first["dry_kg"], first["yield_pct"]) == (
        "2026-02-03",
        "120.5",
        "40.5",
        "33.6",
    )
    assert (second["lot_code"], second["dry_kg"]) == (None, None)
    assert body["totals"][0] == {
        "key": "harvests",
        "label": "Cosechas",
        "kind": "count",
        "value": 2,
    }
    assert body["totals"][1]["value"] == "130.5"
    assert body["generated_at"]


def test_money_comes_as_whole_pesos(auth_client, estate):
    buyer = BuyerFactory(producer=estate.producer)
    sale_with_lines(
        estate.esperanza, buyer=buyer, sale_date=date(2026, 2, 1), lines=(("g1", "10.0", 18500),)
    )

    body = auth_client(estate.owner).get(PRODUCER_URL, {"type": "sales", **PERIOD}).json()

    assert (body["rows"][0]["price_per_kg"], body["rows"][0]["subtotal"]) == (18500, 185000)
    assert body["totals"][-1] == {
        "key": "total_value",
        "label": "Valor total",
        "kind": "money",
        "value": 185000,
    }


def test_without_results_it_is_an_empty_report_and_not_an_error(auth_client, estate):
    response = auth_client(estate.owner).get(PRODUCER_URL, {"type": "quality", **PERIOD})

    assert response.status_code == 200
    assert response.json()["rows"] == []


def test_without_a_type_the_report_is_not_generated(auth_client, estate):
    response = auth_client(estate.owner).get(PRODUCER_URL, PERIOD)

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert set(response.json()["fields"]) == {"type"}


def test_an_end_before_the_start_is_rejected(auth_client, estate):
    response = auth_client(estate.owner).get(
        PRODUCER_URL, {"type": "production", "from": "2026-03-01", "to": "2026-02-01"}
    )

    assert response.status_code == 400
    assert set(response.json()["fields"]) == {"to"}


def test_a_foreign_farm_is_not_found(auth_client, estate):
    response = auth_client(estate.owner).get(
        PRODUCER_URL, {"type": "production", **PERIOD, "farm": str(estate.other_farm.pk)}
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert set(response.json()["fields"]) == {"farm"}


def test_an_employee_without_the_module_permission_is_denied(auth_client, estate):
    employee = estate.employee("warehouse.view_stock", farm=estate.esperanza)

    allowed = auth_client(employee).get(PRODUCER_URL, {"type": "inventory"})
    denied = auth_client(employee).get(PRODUCER_URL, {"type": "sales", **PERIOD})

    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"


def test_without_the_reports_permission_nothing_is_generated(auth_client, estate):
    employee = make_delegate(estate.producer, ["harvests.view_harvest"], farm=estate.esperanza)

    response = auth_client(employee).get(PRODUCER_URL, {"type": "production", **PERIOD})

    assert response.status_code == 403


def test_the_producer_cannot_open_the_association_reports(auth_client, estate):
    response = auth_client(estate.owner).get(ASSOCIATION_URL, {"type": "production", **PERIOD})

    assert response.status_code == 403


def test_the_association_cannot_open_the_producer_reports(auth_client):
    response = auth_client(make_administrator()).get(
        PRODUCER_URL, {"type": "production", **PERIOD}
    )

    assert response.status_code == 403


def test_the_association_report_by_farm(auth_client, estate):
    harvest(estate.rio, date(2026, 2, 1), "100.0")

    response = auth_client(make_administrator()).get(
        ASSOCIATION_URL, {"type": "production", **PERIOD, "producer": str(estate.producer.pk)}
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [(row["farm"], row["green_kg"]) for row in rows] == [
        ("F01 · La Esperanza", "100.0"),
        ("F02 · El Mirador", "0.0"),
    ]
    assert response.json()["filters"][1]["key"] == "producer"


def test_the_association_cannot_ask_for_inventory_or_traceability(auth_client):
    response = auth_client(make_administrator()).get(ASSOCIATION_URL, {"type": "inventory"})

    assert response.status_code == 400
    assert set(response.json()["fields"]) == {"type"}


def test_the_technical_account_opens_both(auth_client, estate):
    technical = UserFactory(is_superuser=True)
    harvest(estate.rio, date(2026, 2, 1), "1.0")

    producer = auth_client(technical).get(PRODUCER_URL, {"type": "production", **PERIOD})
    association = auth_client(technical).get(ASSOCIATION_URL, {"type": "production", **PERIOD})

    assert (producer.status_code, association.status_code) == (200, 200)


def test_a_lot_status_in_traceability_reads_as_shown(auth_client, estate):
    LotFactory(harvest=harvest(estate.rio, date(2026, 2, 1), "5.0"), status=LotStatus.DRYING)

    rows = (
        auth_client(estate.owner)
        .get(PRODUCER_URL, {"type": "traceability", **PERIOD})
        .json()["rows"]
    )

    assert rows[0]["status"] == "En secado"
