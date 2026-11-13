from datetime import date
from decimal import Decimal

import pytest

from apps.common.contracts.indicators import FarmMonthSales, IndicatorPeriod, indicator_source
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.sales.tests.helpers import sale_with_lines

pytestmark = pytest.mark.django_db

PERIOD = IndicatorPeriod(date(2026, 1, 1), date(2026, 3, 31))


def farm_ids(*farms):
    return Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")


def test_the_registered_sales_add_up_by_farm_and_month(django_assert_num_queries):
    farm = FarmFactory()
    # Una venta con dos calibres cuenta como una sola.
    sale_with_lines(
        farm, lines=(("g1", "150.0", 18500), ("g2", "40.0", 15000)), sale_date=date(2026, 1, 1)
    )
    sale_with_lines(farm, lines=(("g1", "10.5", 18500),), sale_date=date(2026, 1, 31))
    sale_with_lines(farm, lines=(("g2", "5.0", 15000),), sale_date=date(2026, 3, 31))

    with django_assert_num_queries(1):
        rows = indicator_source("sales")(farm_ids(farm), PERIOD)

    assert sorted(rows, key=lambda row: row.month) == [
        FarmMonthSales(
            farm_id=farm.pk,
            month="2026-01",
            g1_kg=Decimal("160.5"),
            g2_kg=Decimal("40.0"),
            sales=2,
        ),
        FarmMonthSales(
            farm_id=farm.pk, month="2026-03", g1_kg=Decimal("0.0"), g2_kg=Decimal("5.0"), sales=1
        ),
    ]


def test_voided_sales_and_sales_outside_the_period_or_the_farms_do_not_count():
    farm = FarmFactory()
    sale_with_lines(farm, voided=True, sale_date=date(2026, 2, 1))
    sale_with_lines(farm, sale_date=date(2025, 12, 31))
    sale_with_lines(farm, sale_date=date(2026, 4, 1))
    sale_with_lines(FarmFactory(), sale_date=date(2026, 2, 1))

    assert indicator_source("sales")(farm_ids(farm), PERIOD) == []
