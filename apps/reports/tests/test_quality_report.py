from decimal import Decimal

import pytest

from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.quality.tests.factories import LotClassificationFactory, LotDiscardFactory
from apps.reports.report import Column

from .helpers import PERIOD, Estate, at, dry, generate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Estate()


def classify(plot, when, g1="80.0", g2="15.0", discard="5.0", status=LotStatus.CLASSIFIED):
    lot = LotFactory(harvest__plot=plot, status=status)
    dry(lot, Decimal(g1) + Decimal(g2) + Decimal(discard))
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal(g1),
        g2_kg=Decimal(g2),
        discard_kg=Decimal(discard),
        discard_reason="mold" if Decimal(discard) else "",
        classified_at=when,
    )
    return lot


def discard_whole(plot, when, dry_kg="60.0"):
    lot = LotFactory(harvest__plot=plot, status=LotStatus.DISCARDED)
    dry(lot, dry_kg)
    LotDiscardFactory(lot=lot, reason="other", detail="Se mojó", discarded_at=when)
    return lot


def totals(report):
    return {total.key: total.value for total in report.totals}


def test_the_columns_of_the_quality_report(estate):
    report = generate(estate.owner, type="quality", **PERIOD)

    assert [(column.key, column.kind) for column in report.columns] == [
        ("lot_code", "text"),
        ("farm", "text"),
        ("plot", "text"),
        ("closed_on", "date"),
        ("result", "text"),
        ("dry_kg", "kg"),
        ("g1_kg", "kg"),
        ("g2_kg", "kg"),
        ("discard_kg", "kg"),
        ("g1_pct", "pct"),
        ("g2_pct", "pct"),
        ("discard_pct", "pct"),
        ("discard_reason", "text"),
    ]
    assert report.columns[0] == Column("lot_code", "Lote", "text")


def test_a_classified_lot_with_its_split_and_shares(estate):
    lot = classify(estate.rio, at(2026, 2, 3, 9), g1="290.0", g2="70.0", discard="20.0")

    (row,) = generate(estate.owner, type="quality", **PERIOD).rows

    assert row["lot_code"] == lot.code
    assert row["result"] == "Clasificado"
    assert (row["g1_pct"], row["g2_pct"], row["discard_pct"]) == (
        Decimal("76.3"),
        Decimal("18.4"),
        Decimal("5.3"),
    )
    assert row["discard_reason"] == "Moho"


def test_a_whole_discard_shows_its_reason_with_its_detail(estate):
    discard_whole(estate.rio, at(2026, 2, 3, 9))

    (row,) = generate(estate.owner, type="quality", **PERIOD).rows

    assert (row["result"], row["discard_kg"], row["discard_pct"]) == (
        "Descartado",
        Decimal("60.0"),
        Decimal("100.0"),
    )
    assert row["discard_reason"] == "Otro: Se mojó"


def test_the_totals_add_the_whole_discards_to_the_discard(estate):
    classify(estate.rio, at(2026, 1, 10, 9), g1="80.0", g2="15.0", discard="5.0")
    classify(
        estate.loma,
        at(2026, 1, 11, 9),
        g1="20.0",
        g2="0",
        discard="0",
        status=LotStatus.IN_WAREHOUSE,
    )
    discard_whole(estate.alto, at(2026, 1, 12, 9), dry_kg="80.0")

    assert totals(generate(estate.owner, type="quality", **PERIOD)) == {
        "lots_classified": 2,
        "lots_discarded": 1,
        "classified_kg": Decimal("200.0"),
        "g1_kg": Decimal("100.0"),
        "g2_kg": Decimal("15.0"),
        "discard_kg": Decimal("85.0"),
        "g1_pct": Decimal("50.0"),
        "g2_pct": Decimal("7.5"),
        "discard_pct": Decimal("42.5"),
    }


def test_without_closed_lots_the_shares_are_null(estate):
    report = generate(estate.owner, type="quality", **PERIOD)

    assert report.is_empty
    assert totals(report)["g1_pct"] is None


def test_the_rows_go_by_closing_date(estate):
    late = classify(estate.rio, at(2026, 3, 1, 9))
    early = discard_whole(estate.alto, at(2026, 1, 2, 9))

    rows = generate(estate.owner, type="quality", **PERIOD).rows

    assert [row["lot_code"] for row in rows] == [early.code, late.code]
