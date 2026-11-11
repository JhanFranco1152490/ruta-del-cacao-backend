from decimal import Decimal

import pytest

from apps.common.contracts.indicators import FarmGradeKg, indicator_source
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.warehouse.tests.factories import StockBalanceFactory

pytestmark = pytest.mark.django_db


def farm_ids(*farms):
    return Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")


def balance(farm, grade, kg):
    lot = LotFactory(harvest__plot=characterized_plot(farm=farm), status=LotStatus.IN_WAREHOUSE)
    return StockBalanceFactory(lot=lot, grade=grade, quantity_kg=Decimal(kg))


def test_the_stock_adds_up_by_farm_and_grade_without_the_empty_balances(
    django_assert_num_queries,
):
    farm = FarmFactory()
    balance(farm, "g1", "120.0")
    balance(farm, "g1", "30.5")
    balance(farm, "g2", "0.0")
    balance(FarmFactory(), "g1", "500.0")

    with django_assert_num_queries(1):
        rows = indicator_source("warehouse")(farm_ids(farm))

    assert rows == [FarmGradeKg(farm_id=farm.pk, grade="g1", kg=Decimal("150.5"))]
