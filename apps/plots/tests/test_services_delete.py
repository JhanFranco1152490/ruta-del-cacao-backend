import uuid
from decimal import Decimal
from unittest import mock

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.exceptions import FarmInactive, PlotHasRecords, PlotNotFound, StalePlotVersion
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.services import create_plot, delete_plot, update_plot
from apps.plots.tests.factories import PlotFactory, plot_data
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def farm(owner):
    return FarmFactory(producer=owner.producer, area_hectares=Decimal("10.00"))


def test_deletes_the_plot_frees_its_area_and_keeps_its_history(owner, farm):
    # Criterio 16: la parcela desaparece, sus 3 ha quedan libres y el historial sigue.
    plot, _ = create_plot(owner, plot_data(farm, code="P-error", area_hectares=Decimal("3.00")))
    PlotFactory(farm=farm, area_hectares=Decimal("7.00"))

    delete_plot(owner, plot.pk, 1)

    assert not Plot.objects.filter(pk=plot.pk).exists()
    create_plot(owner, plot_data(farm, code="P-nueva", area_hectares=Decimal("3.00")))
    history = PlotAuditEvent.objects.filter(plot_ref=plot.pk).order_by("occurred_at")
    assert [event.action for event in history] == ["created", "deleted"]
    assert all(event.plot_id is None for event in history)
    assert {event.plot_code for event in history} == {"P-error"}
    assert history.last().actor == owner


def test_a_plot_with_records_that_depend_on_it_is_not_deleted(owner, farm):
    plot = PlotFactory(farm=farm)

    with mock.patch("apps.plots.services.delete.has_dependent_rows", return_value=True):
        with pytest.raises(PlotHasRecords):
            delete_plot(owner, plot.pk, 1)

    assert Plot.objects.filter(pk=plot.pk).exists()
    assert not PlotAuditEvent.objects.filter(action="deleted").exists()


def test_its_own_history_does_not_count_as_a_record(owner, farm):
    plot, _ = create_plot(owner, plot_data(farm))
    update_plot(owner, plot.pk, 1, {"code": "Otro código"})

    delete_plot(owner, plot.pk, 2)

    assert not Plot.objects.filter(pk=plot.pk).exists()


def test_an_outdated_version_is_rejected_with_the_current_plot(owner, farm):
    plot = PlotFactory(farm=farm)
    update_plot(owner, plot.pk, 1, {"code": "Cambiada por otra persona"})

    with pytest.raises(StalePlotVersion) as error:
        delete_plot(owner, plot.pk, 1)

    assert error.value.current_plot.version == 2
    assert Plot.objects.filter(pk=plot.pk).exists()


def test_the_plots_of_an_inactive_farm_cannot_be_deleted(owner, farm):
    # Mientras la finca está inactiva sus parcelas quedan congeladas; al reactivarla vuelven
    # tal como estaban.
    plot = PlotFactory(farm=farm)
    farm.is_active = False
    farm.save()

    with pytest.raises(FarmInactive):
        delete_plot(owner, plot.pk, 1)

    assert Plot.objects.filter(pk=plot.pk).exists()


def test_a_plot_of_another_producer_does_not_exist(farm):
    plot = PlotFactory(farm=farm)
    stranger = UserFactory(producer=ProducerFactory())

    with pytest.raises(PlotNotFound):
        delete_plot(stranger, plot.pk, 1)

    assert Plot.objects.filter(pk=plot.pk).exists()


def test_deleting_twice_reports_that_it_no_longer_exists(owner, farm):
    plot = PlotFactory(farm=farm)
    delete_plot(owner, plot.pk, 1)

    with pytest.raises(PlotNotFound):
        delete_plot(owner, plot.pk, 1)


def test_an_unknown_plot_does_not_exist(owner):
    with pytest.raises(PlotNotFound):
        delete_plot(owner, uuid.uuid4(), 1)
