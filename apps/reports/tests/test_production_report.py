from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.reports.report import Column, Total

from .helpers import PERIOD, Estate, dry, generate, harvest

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Estate()


def totals(report):
    return {total.key: total.value for total in report.totals}


def test_the_columns_of_the_production_report(estate):
    report = generate(estate.owner, type="production", **PERIOD)

    assert report.columns == (
        Column("harvest_date", "Fecha", "date"),
        Column("farm", "Finca", "text"),
        Column("plot", "Parcela", "text"),
        Column("variety", "Variedad", "text"),
        Column("collector", "Recolector", "text"),
        Column("green_kg", "Kg en baba", "kg"),
        Column("lot_code", "Lote", "text"),
        Column("lot_status", "Estado del lote", "text"),
        Column("dry_kg", "Kg seco", "kg"),
        Column("yield_pct", "Rendimiento %", "pct"),
    )


def test_a_harvest_row_with_its_lot_and_its_drying(estate):
    collector = UserFactory(producer=estate.producer, first_name="Ana", last_name="Pérez")
    dried = harvest(estate.rio, date(2026, 2, 3), "120.5", collector=collector)
    lot = LotFactory(harvest=dried, status=LotStatus.IN_WAREHOUSE)
    dry(lot, "40.5", yield_pct="33.6")

    (row,) = generate(estate.owner, type="production", **PERIOD).rows

    assert row == {
        "harvest_date": date(2026, 2, 3),
        "farm": "F01 · La Esperanza",
        "plot": f"{estate.rio.code} · El Río",
        "variety": dried.variety.name,
        "collector": "Ana Pérez",
        "green_kg": Decimal("120.5"),
        "lot_code": lot.code,
        "lot_status": "En bodega",
        "dry_kg": Decimal("40.5"),
        "yield_pct": Decimal("33.6"),
    }


def test_a_harvest_without_lot_or_without_finished_drying_has_empty_cells(estate):
    harvest(estate.rio, date(2026, 2, 3), "50.0")
    LotFactory(harvest=harvest(estate.rio, date(2026, 2, 4), "60.0"))

    rows = generate(estate.owner, type="production", **PERIOD).rows

    assert [(row["lot_code"] is None, row["dry_kg"], row["yield_pct"]) for row in rows] == [
        (True, None, None),
        (False, None, None),
    ]


def test_the_rows_go_by_date_then_farm_then_plot(estate):
    harvest(estate.alto, date(2026, 1, 10), "1.0")
    harvest(estate.loma, date(2026, 1, 10), "2.0")
    harvest(estate.rio, date(2026, 1, 10), "3.0")
    harvest(estate.rio, date(2026, 1, 5), "4.0")

    rows = generate(estate.owner, type="production", **PERIOD).rows

    assert [row["green_kg"] for row in rows] == [
        Decimal("4.0"),
        Decimal("3.0"),
        Decimal("2.0"),
        Decimal("1.0"),
    ]


def test_the_totals_count_the_harvests_and_what_is_not_dried_yet(estate):
    dry(LotFactory(harvest=harvest(estate.rio, date(2026, 2, 1), "100.0")), "35.0")
    harvest(estate.loma, date(2026, 2, 2), "30.5")

    report = generate(estate.owner, type="production", **PERIOD)

    assert report.totals[0] == Total("harvests", "Cosechas", "count", 2)
    assert totals(report) == {
        "harvests": 2,
        "green_kg": Decimal("130.5"),
        "dry_kg": Decimal("35.0"),
        "green_kg_not_dried": Decimal("30.5"),
    }


def test_without_harvests_there_are_no_rows_and_the_totals_are_zero(estate):
    harvest(estate.other_plot, date(2026, 2, 1), "10.0")
    harvest(estate.rio, date(2025, 12, 31), "10.0")

    report = generate(estate.owner, type="production", **PERIOD)

    assert report.rows == []
    assert report.is_empty
    assert totals(report)["green_kg"] == Decimal("0.0")


def test_the_plot_and_the_lot_narrow_the_report(estate):
    harvest(estate.rio, date(2026, 2, 1), "10.0")
    lot = LotFactory(harvest=harvest(estate.loma, date(2026, 2, 1), "20.0"))

    by_plot = generate(estate.owner, type="production", **PERIOD, plot=str(estate.rio.pk))
    by_lot = generate(estate.owner, type="production", **PERIOD, lot=str(lot.pk))

    assert [row["green_kg"] for row in by_plot.rows] == [Decimal("10.0")]
    assert [row["lot_code"] for row in by_lot.rows] == [lot.code]


def test_the_report_takes_a_fixed_number_of_queries(estate, django_assert_max_num_queries):
    for day in range(1, 21):
        dry(LotFactory(harvest=harvest(estate.rio, date(2026, 2, day), "10.0")), "3.5")

    with django_assert_max_num_queries(8):
        report = generate(estate.owner, type="production", **PERIOD, farm=str(estate.esperanza.pk))

    assert len(report.rows) == 20
