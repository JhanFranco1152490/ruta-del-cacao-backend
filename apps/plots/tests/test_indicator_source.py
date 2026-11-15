from decimal import Decimal

import pytest

from apps.common.contracts.indicators import PlotArea, indicator_source
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


def test_the_plots_of_the_farms_come_with_their_declared_area_active_or_not(
    django_assert_num_queries,
):
    farm = FarmFactory()
    active = PlotFactory(farm=farm, area_hectares=Decimal("2.50"))
    inactive = PlotFactory(farm=farm, is_active=False, name=None)
    PlotFactory()

    with django_assert_num_queries(1):
        rows = indicator_source("plots")(Farm.objects.filter(pk=farm.pk).values("pk"))

    assert sorted(rows, key=lambda row: row.code) == [
        PlotArea(
            plot_id=active.pk,
            farm_id=farm.pk,
            code=active.code,
            name=active.name,
            area_hectares=Decimal("2.50"),
            is_active=True,
        ),
        PlotArea(
            plot_id=inactive.pk,
            farm_id=farm.pk,
            code=inactive.code,
            name="",
            area_hectares=inactive.area_hectares,
            is_active=False,
        ),
    ]
