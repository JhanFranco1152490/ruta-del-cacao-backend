from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.buyers.tests.factories import BuyerFactory
from apps.fermentation.tests.factories import FermentationProcessFactory
from apps.lots.choices import LotStatus
from apps.quality.tests.factories import LotDiscardFactory
from apps.sales.tests.helpers import sale_with_lines
from apps.warehouse.tests.factories import WarehouseFactory
from apps.warehouse.tests.helpers import stored_lot

from .helpers import PERIOD, Estate, at, dry, generate, lot_of

pytestmark = pytest.mark.django_db

EMPTY_STAGES = {
    "fermentation_started_on": None,
    "fermentation_ended_on": None,
    "drying_ended_on": None,
    "dry_kg": None,
    "yield_pct": None,
    "quality_result": None,
    "quality_closed_on": None,
    "g1_kg": None,
    "g2_kg": None,
    "discard_kg": None,
    "entry_date": None,
    "available_kg": None,
    "sold_kg": None,
    "buyers": None,
}


@pytest.fixture
def estate():
    return Estate()


def totals(report):
    return {total.key: total.value for total in report.totals}


def test_the_columns_follow_the_lot_from_harvest_to_sale(estate):
    report = generate(estate.owner, type="traceability", **PERIOD)

    assert [column.key for column in report.columns] == [
        "lot_code",
        "farm",
        "plot",
        "harvest_date",
        "green_kg",
        "status",
        *EMPTY_STAGES,
    ]


def test_a_lot_just_formed_shows_only_its_origin(estate):
    lot = lot_of(estate.rio, day=date(2026, 2, 3), kg="120.0")

    (row,) = generate(estate.owner, type="traceability", **PERIOD).rows

    assert row == {
        "lot_code": lot.code,
        "farm": "F01 · La Esperanza",
        "plot": f"{estate.rio.code} · El Río",
        "harvest_date": date(2026, 2, 3),
        "green_kg": Decimal("120.0"),
        "status": "Generado",
        **EMPTY_STAGES,
    }


def test_a_lot_in_the_warehouse_with_a_sale_shows_every_stage(estate):
    lot, entry = stored_lot(
        estate.rio,
        WarehouseFactory(farm=estate.esperanza),
        g1="250.0",
        g2="55.2",
        harvest_date=date(2026, 1, 20),
    )
    FermentationProcessFactory(lot=lot, started_at=at(2026, 1, 21, 8), ended_at=at(2026, 1, 27, 8))
    north = BuyerFactory(producer=estate.producer, name="Cacaos del Norte")
    andes = BuyerFactory(producer=estate.producer, name="Andes Chocolates")
    sale_with_lines(estate.esperanza, lot=lot, buyer=north, lines=(("g1", "100.0", 18500),))
    sale_with_lines(estate.esperanza, lot=lot, buyer=andes, lines=(("g2", "20.0", 15000),))

    (row,) = generate(estate.owner, type="traceability", **PERIOD).rows

    assert row["status"] == "En bodega"
    assert (row["fermentation_started_on"], row["fermentation_ended_on"]) == (
        date(2026, 1, 21),
        date(2026, 1, 27),
    )
    assert row["drying_ended_on"] is not None
    assert row["dry_kg"] == lot.drying.dry_weight_kg
    assert (row["quality_result"], row["g1_kg"], row["g2_kg"], row["discard_kg"]) == (
        "Clasificado",
        Decimal("250.0"),
        Decimal("55.2"),
        Decimal("0.0"),
    )
    assert row["entry_date"] == entry.entry_date
    # Las ventas de la prueba no descuentan existencias: quedan las del ingreso.
    assert row["available_kg"] == Decimal("305.2")
    assert row["sold_kg"] == Decimal("120.0")
    assert row["buyers"] == "Andes Chocolates, Cacaos del Norte"


def test_a_lot_discarded_whole_keeps_its_history(estate):
    lot = lot_of(estate.rio, status=LotStatus.DISCARDED)
    dry(lot, "60.0")
    LotDiscardFactory(lot=lot, discarded_at=at(2026, 3, 1, 9))

    (row,) = generate(estate.owner, type="traceability", **PERIOD).rows

    assert (row["status"], row["quality_result"], row["discard_kg"]) == (
        "Descartado",
        "Descartado",
        Decimal("60.0"),
    )
    assert row["quality_closed_on"] == date(2026, 3, 1)


def test_the_totals_add_the_lots_and_their_kg(estate):
    dry(lot_of(estate.rio, kg="100.0"), "35.0")
    lot_of(estate.alto, kg="50.0")
    lot_of(estate.other_plot, kg="999.0")

    assert totals(generate(estate.owner, type="traceability", **PERIOD)) == {
        "lots": 2,
        "green_kg": Decimal("150.0"),
        "dry_kg": Decimal("35.0"),
        "sold_kg": Decimal("0.0"),
    }


def test_the_lot_filter_gives_just_that_lot(estate):
    lot_of(estate.rio)
    wanted = lot_of(estate.loma)

    rows = generate(estate.owner, type="traceability", **PERIOD, lot=str(wanted.pk)).rows

    assert [row["lot_code"] for row in rows] == [wanted.code]


def queries_for(owner):
    owner = type(owner).objects.get(pk=owner.pk)
    with CaptureQueriesContext(connection) as queries:
        report = generate(owner, type="traceability", **PERIOD)
    return len(queries), len(report.rows)


def test_the_queries_do_not_grow_with_the_lots(estate):
    dry(lot_of(estate.rio, day=date(2026, 2, 1)), "30.0")
    one = queries_for(estate.owner)
    for day in range(2, 16):
        dry(lot_of(estate.rio, day=date(2026, 2, day)), "30.0")

    assert queries_for(estate.owner) == (one[0], 15)
