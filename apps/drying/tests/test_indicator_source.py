from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.contracts.indicators import IndicatorPeriod, PlotMonthDried, indicator_source
from apps.drying.tests.factories import DryingProcessFactory
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot

pytestmark = pytest.mark.django_db

PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))


def farm_ids(*farms):
    return Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")


def dried(harvest, dry_kg):
    return DryingProcessFactory(
        lot__harvest=harvest,
        ended_at=timezone.now(),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=dry_kg,
        yield_pct=Decimal("35.0"),
        total_sun_hours=Decimal("40.0"),
    )


def test_the_finished_dryings_count_in_the_month_of_the_harvest(django_assert_num_queries):
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    # El secado termina hoy, meses después: cuenta en enero, cuando se cosechó.
    dried(
        HarvestFactory(plot=plot, harvest_date=date(2026, 1, 5), green_weight_kg=Decimal("100.0")),
        Decimal("36.0"),
    )
    dried(
        HarvestFactory(plot=plot, harvest_date=date(2026, 1, 20), green_weight_kg=Decimal("50.0")),
        Decimal("17.5"),
    )

    with django_assert_num_queries(1):
        rows = indicator_source("drying")(farm_ids(farm), PERIOD)

    assert rows == [
        PlotMonthDried(
            plot_id=plot.pk,
            farm_id=farm.pk,
            month="2026-01",
            dry_kg=Decimal("53.5"),
            green_kg=Decimal("150.0"),
        )
    ]


def test_a_drying_in_progress_does_not_count():
    farm = FarmFactory()
    DryingProcessFactory(
        lot__harvest=HarvestFactory(
            plot=characterized_plot(farm=farm), harvest_date=date(2026, 2, 1)
        )
    )

    assert indicator_source("drying")(farm_ids(farm), PERIOD) == []


def test_the_dryings_of_harvests_outside_the_period_or_the_farms_do_not_count():
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    dried(HarvestFactory(plot=plot, harvest_date=date(2025, 12, 31)), Decimal("30.0"))
    dried(HarvestFactory(plot=plot, harvest_date=date(2026, 4, 1)), Decimal("30.0"))
    dried(
        HarvestFactory(plot=characterized_plot(), harvest_date=date(2026, 2, 1)), Decimal("30.0")
    )

    assert indicator_source("drying")(farm_ids(farm), PERIOD) == []
