from datetime import date
from decimal import Decimal

import pytest

from apps.buyers.tests.factories import BuyerFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.reports.report import Total
from apps.sales.tests.helpers import sale_with_lines

from .helpers import PERIOD, Estate, generate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Estate()


def totals(report):
    return {total.key: total.value for total in report.totals}


def test_each_line_of_a_registered_sale_is_a_row_with_its_price(estate):
    lot = LotFactory(harvest__plot=estate.rio, status=LotStatus.IN_WAREHOUSE)
    buyer = BuyerFactory(producer=estate.producer, name="Cacaos del Norte")
    sale = sale_with_lines(
        estate.esperanza,
        lot=lot,
        buyer=buyer,
        number=12,
        sale_date=date(2026, 2, 3),
        lines=(("g1", "150.0", 18500), ("g2", "40.0", 15000)),
    )

    report = generate(estate.owner, type="sales", **PERIOD)

    assert [(column.key, column.kind) for column in report.columns] == [
        ("sale_date", "date"),
        ("sale_number", "text"),
        ("buyer", "text"),
        ("farm", "text"),
        ("lot_code", "text"),
        ("grade", "text"),
        ("kg", "kg"),
        ("price_per_kg", "money"),
        ("subtotal", "money"),
    ]
    assert report.rows == [
        {
            "sale_date": date(2026, 2, 3),
            "sale_number": "V-0012",
            "buyer": "Cacaos del Norte",
            "farm": "F01 · La Esperanza",
            "lot_code": lot.code,
            "grade": grade,
            "kg": Decimal(kg),
            "price_per_kg": price,
            "subtotal": subtotal,
        }
        for grade, kg, price, subtotal in (
            ("G1", "150.0", 18500, 2775000),
            ("G2", "40.0", 15000, 600000),
        )
    ]
    assert sale.lines.count() == 2


def test_the_totals_count_each_sale_once_and_add_the_value(estate):
    sale_with_lines(
        estate.esperanza,
        sale_date=date(2026, 1, 10),
        lines=(("g1", "100.0", 18000), ("g2", "20.0", 15000)),
    )
    sale_with_lines(estate.mirador, sale_date=date(2026, 2, 10), lines=(("g1", "50.5", 20000),))
    sale_with_lines(estate.esperanza, sale_date=date(2026, 2, 11), voided=True)

    report = generate(estate.owner, type="sales", **PERIOD)

    assert report.totals[-1] == Total("total_value", "Valor total", "money", 3110000)
    assert totals(report) == {
        "sales": 2,
        "g1_kg": Decimal("150.5"),
        "g2_kg": Decimal("20.0"),
        "sold_kg": Decimal("170.5"),
        "total_value": 3110000,
    }


def test_the_rows_go_by_date_then_number(estate):
    sale_with_lines(estate.esperanza, number=7, sale_date=date(2026, 2, 1))
    sale_with_lines(estate.esperanza, number=5, sale_date=date(2026, 2, 1))
    sale_with_lines(estate.esperanza, number=9, sale_date=date(2026, 1, 1))

    rows = generate(estate.owner, type="sales", **PERIOD).rows

    assert [row["sale_number"] for row in rows] == ["V-0009", "V-0005", "V-0007"]


def test_another_producer_sales_do_not_show(estate):
    sale_with_lines(estate.other_farm, sale_date=date(2026, 2, 1))

    assert generate(estate.owner, type="sales", **PERIOD).is_empty
