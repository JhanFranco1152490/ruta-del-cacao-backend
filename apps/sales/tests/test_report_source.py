from datetime import date
from decimal import Decimal

import pytest

from apps.buyers.tests.factories import BuyerFactory
from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import LotSales, SaleRow, report_source
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.sales.tests.helpers import sale_with_lines

pytestmark = pytest.mark.django_db

PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))


def sale_rows(*farms, **filters):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("sale_rows")(farm_ids, PERIOD, **filters)


def test_each_line_of_a_registered_sale_is_a_row(django_assert_num_queries):
    farm = FarmFactory(name="La Esperanza")
    buyer = BuyerFactory(producer=farm.producer, name="Cacaos del Norte")
    sale = sale_with_lines(
        farm,
        lines=(("g1", "150.0", 18500), ("g2", "40.0", 15000)),
        buyer=buyer,
        sale_date=date(2026, 2, 3),
    )
    g1_line, g2_line = sale.lines.order_by("grade")

    with django_assert_num_queries(1):
        rows = sale_rows(farm)

    def row(line, grade, kg, price, subtotal):
        return SaleRow(
            sale_id=sale.pk,
            sale_number=sale.number,
            sale_date=date(2026, 2, 3),
            buyer="Cacaos del Norte",
            farm_id=farm.pk,
            farm_code=farm.code,
            farm_name="La Esperanza",
            lot_id=line.lot_id,
            lot_code=line.lot.code,
            grade=grade,
            kg=Decimal(kg),
            price_per_kg=price,
            subtotal=subtotal,
        )

    assert sorted(rows, key=lambda r: r.grade) == [
        row(g1_line, "G1", "150.0", 18500, 2775000),
        row(g2_line, "G2", "40.0", 15000, 600000),
    ]


def test_voided_sales_sales_outside_the_period_and_other_farms_do_not_count():
    farm = FarmFactory()
    first = sale_with_lines(farm, sale_date=date(2026, 1, 1))
    last = sale_with_lines(farm, sale_date=date(2026, 3, 31))
    sale_with_lines(farm, sale_date=date(2026, 2, 1), voided=True)
    sale_with_lines(farm, sale_date=date(2025, 12, 31))
    sale_with_lines(farm, sale_date=date(2026, 4, 1))
    sale_with_lines(FarmFactory(), sale_date=date(2026, 2, 1))

    assert {row.sale_id for row in sale_rows(farm)} == {first.pk, last.pk}


def test_the_plot_and_the_lot_narrow_the_lines():
    farm = FarmFactory()
    plot = characterized_plot(farm=farm)
    mine = sale_with_lines(farm, plot=plot, sale_date=date(2026, 2, 1))
    theirs = sale_with_lines(farm, sale_date=date(2026, 2, 1))
    their_lot = theirs.lines.get().lot_id

    assert [row.sale_id for row in sale_rows(farm, plot_id=plot.pk)] == [mine.pk]
    assert [row.lot_id for row in sale_rows(farm, lot_id=their_lot)] == [their_lot]


def test_by_lot_adds_the_registered_kg_and_lists_each_buyer_once(django_assert_num_queries):
    farm = FarmFactory()
    lot = LotFactory(harvest__plot=characterized_plot(farm=farm), status=LotStatus.IN_WAREHOUSE)
    north = BuyerFactory(producer=farm.producer, name="Cacaos del Norte")
    andes = BuyerFactory(producer=farm.producer, name="Andes Chocolates")
    sale_with_lines(farm, lot=lot, buyer=north, lines=(("g1", "100.0", 18500),))
    sale_with_lines(farm, lot=lot, buyer=north, lines=(("g2", "20.0", 15000),))
    sale_with_lines(farm, lot=lot, buyer=andes, lines=(("g1", "30.0", 18500),))
    sale_with_lines(farm, lot=lot, buyer=andes, lines=(("g1", "99.0", 18500),), voided=True)

    with django_assert_num_queries(1):
        rows = report_source("sales_by_lot")([lot.pk])

    assert rows == [
        LotSales(
            lot_id=lot.pk,
            sold_kg=Decimal("150.0"),
            buyers=("Andes Chocolates", "Cacaos del Norte"),
        )
    ]
    with django_assert_num_queries(0):
        assert report_source("sales_by_lot")([]) == []
