from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import HarvestRow, PlotPlace, report_source
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db

PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))


def harvest_rows(*farms, **filters):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("harvest_rows")(farm_ids, PERIOD, **filters)


def test_a_harvest_comes_with_its_place_variety_collector_and_lot(django_assert_num_queries):
    farm = FarmFactory(name="La Esperanza")
    plot = characterized_plot(farm=farm, name="Lote del río")
    collector = UserFactory(producer=farm.producer, first_name="Ana", last_name="Pérez")
    harvest = HarvestFactory(
        plot=plot,
        harvest_date=date(2026, 2, 3),
        green_weight_kg=Decimal("120.5"),
        collector=collector,
    )
    lot = LotFactory(harvest=harvest, status=LotStatus.IN_WAREHOUSE)

    with django_assert_num_queries(1):
        rows = harvest_rows(farm)

    assert rows == [
        HarvestRow(
            harvest_id=harvest.pk,
            harvest_date=date(2026, 2, 3),
            place=PlotPlace(
                farm_id=farm.pk,
                farm_code=farm.code,
                farm_name="La Esperanza",
                plot_id=plot.pk,
                plot_code=plot.code,
                plot_name="Lote del río",
            ),
            variety=harvest.variety.name,
            collector="Ana Pérez",
            green_kg=Decimal("120.5"),
            lot_id=lot.pk,
            lot_code=lot.code,
            lot_status="En bodega",
        )
    ]


def test_a_harvest_without_a_lot_has_no_lot_fields():
    harvest = HarvestFactory(harvest_date=date(2026, 1, 10))

    (row,) = harvest_rows(harvest.plot.farm)

    assert (row.lot_id, row.lot_code, row.lot_status) == (None, None, None)


def test_a_collector_without_a_name_shows_its_email():
    harvest = HarvestFactory(harvest_date=date(2026, 1, 10))
    harvest.collector.first_name = harvest.collector.last_name = ""
    harvest.collector.save()

    (row,) = harvest_rows(harvest.plot.farm)

    assert row.collector == harvest.collector.email


def test_only_the_harvests_of_the_period_count_both_edges_included():
    plot = characterized_plot()
    first = HarvestFactory(plot=plot, harvest_date=date(2026, 1, 1))
    last = HarvestFactory(plot=plot, harvest_date=date(2026, 3, 31))
    HarvestFactory(plot=plot, harvest_date=date(2025, 12, 31))
    HarvestFactory(plot=plot, harvest_date=date(2026, 4, 1))

    assert {row.harvest_id for row in harvest_rows(plot.farm)} == {first.pk, last.pk}


def test_the_harvests_of_another_farm_do_not_count():
    HarvestFactory(harvest_date=date(2026, 1, 10))
    mine = FarmFactory()

    assert harvest_rows(mine) == []


def test_the_plot_and_the_lot_narrow_the_harvests():
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    other_plot = characterized_plot(farm=farm)
    in_plot = HarvestFactory(plot=plot, harvest_date=date(2026, 1, 10))
    HarvestFactory(plot=other_plot, harvest_date=date(2026, 1, 10))
    lot = LotFactory(harvest=HarvestFactory(plot=other_plot, harvest_date=date(2026, 1, 12)))

    assert [row.harvest_id for row in harvest_rows(farm, plot_id=plot.pk)] == [in_plot.pk]
    assert [row.harvest_id for row in harvest_rows(farm, lot_id=lot.pk)] == [lot.harvest_id]
