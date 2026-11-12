from decimal import Decimal

import pytest

from apps.warehouse.tests.factories import WarehouseFactory
from apps.warehouse.tests.helpers import stored_lot

from .helpers import Estate, generate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Estate()


def totals(report):
    return {total.key: total.value for total in report.totals}


def test_each_grade_in_stock_is_a_row(estate):
    warehouse = WarehouseFactory(farm=estate.esperanza, name="Bodega principal")
    lot, entry = stored_lot(estate.rio, warehouse, g1="250.0", g2="55.2", location="Estante 3")

    report = generate(estate.owner, type="inventory")

    assert [(column.key, column.kind) for column in report.columns] == [
        ("lot_code", "text"),
        ("farm", "text"),
        ("warehouse", "text"),
        ("location", "text"),
        ("grade", "text"),
        ("kg", "kg"),
        ("entry_date", "date"),
    ]
    assert report.rows == [
        {
            "lot_code": lot.code,
            "farm": "F01 · La Esperanza",
            "warehouse": "Bodega principal",
            "location": "Estante 3",
            "grade": grade,
            "kg": Decimal(kg),
            "entry_date": entry.entry_date,
        }
        for grade, kg in (("G1", "250.0"), ("G2", "55.2"))
    ]


def test_the_totals_split_the_grades(estate):
    stored_lot(estate.rio, WarehouseFactory(farm=estate.esperanza), g1="250.0", g2="55.2")
    stored_lot(estate.alto, WarehouseFactory(farm=estate.mirador), g1="10.0", g2="0")

    assert totals(generate(estate.owner, type="inventory")) == {
        "g1_kg": Decimal("260.0"),
        "g2_kg": Decimal("55.2"),
        "total_kg": Decimal("315.2"),
    }


def test_the_rows_go_by_farm_then_lot_then_grade(estate):
    mirador, _ = stored_lot(estate.alto, WarehouseFactory(farm=estate.mirador))
    esperanza, _ = stored_lot(estate.rio, WarehouseFactory(farm=estate.esperanza))

    rows = generate(estate.owner, type="inventory").rows

    assert [(row["lot_code"], row["grade"]) for row in rows] == [
        (esperanza.code, "G1"),
        (esperanza.code, "G2"),
        (mirador.code, "G1"),
        (mirador.code, "G2"),
    ]


def test_another_producer_stock_does_not_show(estate):
    stored_lot(estate.other_plot, WarehouseFactory(farm=estate.other_farm))

    assert generate(estate.owner, type="inventory").is_empty
