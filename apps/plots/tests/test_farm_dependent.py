from unittest import mock

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.farm_dependents import registered_dependents
from apps.farms.exceptions import FarmHasRecords
from apps.farms.models import Farm
from apps.farms.services import delete_farm
from apps.farms.tests.factories import FarmFactory
from apps.plots.farm_dependent import plots_dependent
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


def test_the_registry_has_plots_after_startup():
    assert "plots" in {dependent.name for dependent in registered_dependents()}


def test_plots_without_records_are_not_important_and_are_counted():
    farm = FarmFactory()
    PlotFactory.create_batch(2, farm=farm)
    PlotFactory()  # de otra finca

    assert plots_dependent.important_record(farm) is None
    assert plots_dependent.count(farm) == 2


def test_a_plot_with_records_is_important():
    farm = FarmFactory()
    PlotFactory(farm=farm)
    busy = PlotFactory(farm=farm, code="Con registros")

    with mock.patch(
        "apps.plots.services.delete.has_dependent_rows", side_effect=lambda plot, **_: plot == busy
    ):
        reason = plots_dependent.important_record(farm)

    assert "Con registros" in reason


def test_deleting_all_removes_only_that_farms_plots_and_audits_each_one(owner):
    farm = FarmFactory(producer=owner.producer)
    mine = PlotFactory.create_batch(2, farm=farm)
    other = PlotFactory()

    plots_dependent.delete_all(farm, owner)

    assert not Plot.objects.filter(farm=farm).exists()
    assert Plot.objects.filter(pk=other.pk).exists()
    events = PlotAuditEvent.objects.filter(
        plot_ref__in=[plot.pk for plot in mine], action=PlotAuditEvent.Action.DELETED
    )
    assert events.count() == 2
    assert {event.actor for event in events} == {owner}


def test_deleting_a_farm_removes_its_unimportant_plots_with_it(owner):
    farm = FarmFactory(producer=owner.producer)
    plot = PlotFactory(farm=farm)

    delete_farm(owner, farm.pk, farm.version)

    assert not Farm.objects.filter(pk=farm.pk).exists()
    assert not Plot.objects.filter(pk=plot.pk).exists()
    assert PlotAuditEvent.objects.filter(plot_ref=plot.pk, action="deleted").exists()


def test_a_farm_whose_plot_has_records_is_kept_with_all_its_plots(owner):
    farm = FarmFactory(producer=owner.producer)
    plots = PlotFactory.create_batch(2, farm=farm)

    with mock.patch(
        "apps.plots.services.delete.has_dependent_rows",
        side_effect=lambda plot, **_: plot == plots[1],
    ):
        with pytest.raises(FarmHasRecords):
            delete_farm(owner, farm.pk, farm.version)

    assert Plot.objects.filter(farm=farm).count() == 2
