from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import PlotPlace, QualityRow, report_source
from apps.drying.tests.factories import DryingProcessFactory
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.quality.tests.factories import LotClassificationFactory, LotDiscardFactory

pytestmark = pytest.mark.django_db

PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))
BOGOTA = ZoneInfo("America/Bogota")


def at(*moment):
    return datetime(*moment, tzinfo=BOGOTA)


def quality_rows(*farms, **filters):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("quality_rows")(farm_ids, PERIOD, **filters)


def dried(plot, status, dry_kg="100.0"):
    lot = LotFactory(harvest__plot=plot, status=status)
    DryingProcessFactory(
        lot=lot,
        ended_at=timezone.now(),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal(dry_kg),
        yield_pct=Decimal("35.0"),
        total_sun_hours=Decimal("40.0"),
    )
    return lot


def classified(plot, when, status=LotStatus.CLASSIFIED, discard="5.0"):
    lot = dried(plot, status)
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal("80.0"),
        g2_kg=Decimal("15.0"),
        discard_kg=Decimal(discard),
        discard_reason="mold" if Decimal(discard) else "",
        classified_at=when,
    )
    return lot


def discarded(plot, when):
    lot = dried(plot, LotStatus.DISCARDED, dry_kg="60.0")
    LotDiscardFactory(lot=lot, reason="other", detail="Se mojó", discarded_at=when)
    return lot


def test_a_classified_lot_comes_with_its_split_and_reason(django_assert_num_queries):
    plot = characterized_plot()
    lot = classified(plot, at(2026, 2, 3, 9))

    with django_assert_num_queries(1):
        rows = quality_rows(plot.farm)

    assert rows == [
        QualityRow(
            lot_id=lot.pk,
            lot_code=lot.code,
            place=PlotPlace.of(plot),
            closed_on=date(2026, 2, 3),
            result="Clasificado",
            whole_discard=False,
            dry_kg=Decimal("100.0"),
            g1_kg=Decimal("80.0"),
            g2_kg=Decimal("15.0"),
            discard_kg=Decimal("5.0"),
            discard_reason="Moho",
            discard_detail="",
        )
    ]


def test_a_lot_already_in_the_warehouse_is_still_a_classified_one():
    plot = characterized_plot()
    classified(plot, at(2026, 2, 3, 9), status=LotStatus.IN_WAREHOUSE, discard="0")

    (row,) = quality_rows(plot.farm)

    assert (row.result, row.discard_reason) == ("Clasificado", "")


def test_a_whole_discard_puts_all_its_dry_weight_in_the_discard():
    plot = characterized_plot()
    discarded(plot, at(2026, 3, 1, 10))

    (row,) = quality_rows(plot.farm)

    assert (row.result, row.whole_discard, row.g1_kg, row.g2_kg, row.discard_kg) == (
        "Descartado",
        True,
        Decimal("0"),
        Decimal("0"),
        Decimal("60.0"),
    )
    assert (row.discard_reason, row.discard_detail) == ("Otro", "Se mojó")


def test_the_closing_date_is_local_at_both_edges_of_the_period():
    plot = characterized_plot()
    first = classified(plot, at(2026, 1, 1, 0, 5))
    last = classified(plot, at(2026, 3, 31, 23, 30))
    classified(plot, at(2025, 12, 31, 23, 55))
    classified(plot, at(2026, 4, 1, 0, 5))

    assert {row.lot_id for row in quality_rows(plot.farm)} == {first.pk, last.pk}


def test_lots_still_open_and_of_other_farms_do_not_count():
    plot = characterized_plot()
    dried(plot, LotStatus.EVALUATED)
    classified(characterized_plot(), at(2026, 2, 3, 9))

    assert quality_rows(plot.farm) == []


def test_the_plot_and_the_lot_narrow_the_lots():
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    other = characterized_plot(farm=farm)
    mine = classified(plot, at(2026, 2, 3, 9))
    theirs = discarded(other, at(2026, 2, 4, 9))

    assert [row.lot_id for row in quality_rows(farm, plot_id=plot.pk)] == [mine.pk]
    assert [row.lot_id for row in quality_rows(farm, lot_id=theirs.pk)] == [theirs.pk]


def test_by_lot_gives_the_closing_of_the_closed_ones_whenever_it_was(django_assert_num_queries):
    plot = characterized_plot()
    old = classified(plot, at(2025, 6, 1, 9))
    still_open = dried(plot, LotStatus.EVALUATED)

    with django_assert_num_queries(1):
        rows = report_source("quality_by_lot")([old.pk, still_open.pk])

    assert [row.lot_id for row in rows] == [old.pk]
    with django_assert_num_queries(0):
        assert report_source("quality_by_lot")([]) == []
