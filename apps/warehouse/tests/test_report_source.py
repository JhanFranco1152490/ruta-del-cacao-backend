from decimal import Decimal

import pytest

from apps.common.contracts.reports import LotStock, PlotPlace, StockRow, report_source
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.warehouse.tests.factories import WarehouseFactory
from apps.warehouse.tests.helpers import stored_lot

pytestmark = pytest.mark.django_db


def stock_rows(*farms, **filters):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("stock_rows")(farm_ids, **filters)


def test_each_grade_with_stock_is_a_row_with_its_place_and_entry(django_assert_num_queries):
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    warehouse = WarehouseFactory(farm=farm, name="Bodega principal")
    lot, entry = stored_lot(plot, warehouse, g1="250.0", g2="55.2", location="Estante 3")

    with django_assert_num_queries(1):
        rows = stock_rows(farm)

    def row(grade, kg):
        return StockRow(
            lot_id=lot.pk,
            lot_code=lot.code,
            place=PlotPlace.of(plot),
            warehouse="Bodega principal",
            location="Estante 3",
            grade=grade,
            kg=Decimal(kg),
            entry_date=entry.entry_date,
        )

    assert sorted(rows, key=lambda r: r.grade) == [row("G1", "250.0"), row("G2", "55.2")]


def test_a_grade_without_stock_and_other_farms_do_not_count():
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    stored_lot(plot, WarehouseFactory(farm=farm), g1="0", g2="40.0")
    other = FarmFactory()
    stored_lot(characterized_plot(farm=other), WarehouseFactory(farm=other))

    assert [row.grade for row in stock_rows(farm)] == ["G2"]


def test_the_plot_and_the_lot_narrow_the_stock():
    farm = FarmFactory()
    warehouse = WarehouseFactory(farm=farm)
    plot = characterized_plot(farm=farm)
    mine, _ = stored_lot(plot, warehouse, g2="0")
    theirs, _ = stored_lot(characterized_plot(farm=farm), warehouse, g2="0")

    assert [row.lot_id for row in stock_rows(farm, plot_id=plot.pk)] == [mine.pk]
    assert [row.lot_id for row in stock_rows(farm, lot_id=theirs.pk)] == [theirs.pk]


def test_by_lot_gives_the_entry_and_what_is_left_today(django_assert_num_queries):
    farm = FarmFactory()
    warehouse = WarehouseFactory(farm=farm)
    lot, entry = stored_lot(characterized_plot(farm=farm), warehouse, g1="250.0", g2="55.2")

    with django_assert_num_queries(1):
        rows = report_source("stock_by_lot")([lot.pk])

    assert rows == [
        LotStock(lot_id=lot.pk, entry_date=entry.entry_date, available_kg=Decimal("305.2"))
    ]
    with django_assert_num_queries(0):
        assert report_source("stock_by_lot")([]) == []


def test_a_lot_whose_stock_ran_out_still_has_its_entry():
    farm = FarmFactory()
    warehouse = WarehouseFactory(farm=farm)
    lot, _ = stored_lot(characterized_plot(farm=farm), warehouse)
    lot.stock_balances.update(quantity_kg=Decimal("0"))

    (row,) = report_source("stock_by_lot")([lot.pk])

    assert row.available_kg == Decimal("0")
