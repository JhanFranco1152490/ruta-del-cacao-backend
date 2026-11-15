from datetime import date
from decimal import Decimal

import pytest

from apps.common.contracts.indicators import IndicatorPeriod, PlotMonthKg, indicator_source
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot

pytestmark = pytest.mark.django_db

PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))


def farm_ids(*farms):
    return Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")


def test_the_green_kg_are_added_by_plot_and_harvest_month(django_assert_num_queries):
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    HarvestFactory(plot=plot, harvest_date=date(2026, 1, 1), green_weight_kg=Decimal("100.5"))
    HarvestFactory(plot=plot, harvest_date=date(2026, 1, 31), green_weight_kg=Decimal("20.0"))
    HarvestFactory(plot=plot, harvest_date=date(2026, 3, 31), green_weight_kg=Decimal("7.5"))

    with django_assert_num_queries(1):
        rows = indicator_source("harvests")(farm_ids(farm), PERIOD)

    assert sorted(rows, key=lambda row: row.month) == [
        PlotMonthKg(plot_id=plot.pk, farm_id=farm.pk, month="2026-01", kg=Decimal("120.5")),
        PlotMonthKg(plot_id=plot.pk, farm_id=farm.pk, month="2026-03", kg=Decimal("7.5")),
    ]


def test_the_harvests_outside_the_period_or_the_farms_do_not_count():
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    HarvestFactory(plot=plot, harvest_date=date(2025, 12, 31))
    HarvestFactory(plot=plot, harvest_date=date(2026, 4, 1))
    HarvestFactory(plot=characterized_plot(), harvest_date=date(2026, 2, 10))

    assert indicator_source("harvests")(farm_ids(farm), PERIOD) == []


def test_the_green_kg_are_added_by_variety(django_assert_num_queries):
    farm = FarmFactory()
    first, second = CacaoVarietyFactory(), CacaoVarietyFactory()
    HarvestFactory(
        plot=characterized_plot(farm=farm, variety=first), harvest_date=date(2026, 1, 5)
    )
    HarvestFactory(
        plot=characterized_plot(farm=farm, variety=first),
        harvest_date=date(2026, 3, 5),
        green_weight_kg=Decimal("10.5"),
    )
    HarvestFactory(
        plot=characterized_plot(farm=farm, variety=second),
        harvest_date=date(2026, 2, 5),
        green_weight_kg=Decimal("7.0"),
    )
    HarvestFactory(
        plot=characterized_plot(farm=farm, variety=second), harvest_date=date(2025, 1, 1)
    )

    with django_assert_num_queries(1):
        rows = indicator_source("harvest_varieties")(farm_ids(farm), PERIOD)

    by_variety = {row.variety_id: row for row in rows}
    assert by_variety[second.pk].kg == Decimal("7.0")
    assert by_variety[first.pk].name == first.name
    assert len(rows) == 2
