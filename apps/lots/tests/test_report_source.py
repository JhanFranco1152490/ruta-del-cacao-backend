import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import LotRow, PlotPlace, ScopedLot, report_source
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db


def lot_in_scope(farms, lot_id):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("lot_in_scope")(farm_ids, lot_id)


def test_a_lot_of_the_scope_comes_with_its_code_plot_and_farm(django_assert_num_queries):
    lot = LotFactory()
    plot = lot.harvest.plot

    with django_assert_num_queries(1):
        found = lot_in_scope([plot.farm], lot.pk)

    assert found == ScopedLot(lot_id=lot.pk, farm_id=plot.farm_id, plot_id=plot.pk, code=lot.code)


def test_a_lot_of_another_farm_is_not_in_the_scope():
    lot = LotFactory()
    other = LotFactory()

    assert lot_in_scope([other.harvest.plot.farm], lot.pk) is None


def test_a_lot_that_does_not_exist_is_not_in_the_scope():
    lot = LotFactory()

    assert lot_in_scope([lot.harvest.plot.farm], uuid.uuid4()) is None


PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))


def lot_rows(*farms, **filters):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("lot_rows")(farm_ids, PERIOD, **filters)


def test_a_lot_comes_with_its_harvest_and_place(django_assert_num_queries):
    lot = LotFactory(
        harvest__harvest_date=date(2026, 2, 3),
        harvest__green_weight_kg=Decimal("88.0"),
        status=LotStatus.DRIED,
    )
    plot = lot.harvest.plot

    with django_assert_num_queries(1):
        rows = lot_rows(plot.farm)

    assert rows == [
        LotRow(
            lot_id=lot.pk,
            code=lot.code,
            status="Seco",
            harvest_date=date(2026, 2, 3),
            place=PlotPlace.of(plot),
            green_kg=Decimal("88.0"),
        )
    ]


def test_the_lots_count_by_the_date_of_their_harvest():
    inside = LotFactory(harvest__harvest_date=date(2026, 3, 31))
    farm = inside.harvest.plot.farm
    LotFactory(
        harvest__plot=inside.harvest.plot,
        harvest__harvest_date=date(2026, 4, 1),
    )

    assert [row.lot_id for row in lot_rows(farm)] == [inside.pk]


def test_the_plot_and_the_lot_narrow_the_lots():
    lot = LotFactory(harvest__harvest_date=date(2026, 1, 10))
    farm = lot.harvest.plot.farm
    other = LotFactory(
        harvest__plot=characterized_plot(farm=farm), harvest__harvest_date=date(2026, 1, 10)
    )

    assert [row.lot_id for row in lot_rows(farm, plot_id=lot.harvest.plot_id)] == [lot.pk]
    assert [row.lot_id for row in lot_rows(farm, lot_id=other.pk)] == [other.pk]
    assert lot_rows(FarmFactory()) == []
