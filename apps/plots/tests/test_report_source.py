import pytest

from apps.common.contracts.reports import ScopedPlot, report_source
from apps.farms.models import Farm
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


def plot_in_scope(farms, plot_id):
    farm_ids = Farm.objects.filter(pk__in=[farm.pk for farm in farms]).values("pk")
    return report_source("plot_in_scope")(farm_ids, plot_id)


def test_a_plot_of_the_scope_comes_with_its_code_name_and_farm(django_assert_num_queries):
    plot = PlotFactory(name="Lote del río")

    with django_assert_num_queries(1):
        found = plot_in_scope([plot.farm], plot.pk)

    assert found == ScopedPlot(
        plot_id=plot.pk, farm_id=plot.farm_id, code=plot.code, name="Lote del río"
    )


def test_a_plot_without_a_name_has_an_empty_one():
    plot = PlotFactory(name=None)

    assert plot_in_scope([plot.farm], plot.pk).name == ""


def test_a_plot_of_another_farm_is_not_in_the_scope():
    plot = PlotFactory()
    other = PlotFactory()

    assert plot_in_scope([other.farm], plot.pk) is None
