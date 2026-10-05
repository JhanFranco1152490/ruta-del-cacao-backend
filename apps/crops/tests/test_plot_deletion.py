"""La ficha es un registro de la parcela: impide eliminarla, y con ella a su finca y a su
productor. Se prueba por las APIs de esas apps, que no saben nada de las fichas."""

import pytest

from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.crops.models import PlotCharacterization, PlotPlanting
from apps.crops.tests.factories import PlotPlantingFactory
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot
from apps.plots.tests.factories import PlotFactory
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def characterized_plot(farm):
    plot = PlotFactory(farm=farm)
    PlotPlantingFactory(characterization__plot=plot)
    return plot


def assert_characterization_kept(plot):
    assert PlotCharacterization.objects.filter(pk=plot.pk).exists()
    assert PlotPlanting.objects.filter(characterization_id=plot.pk).exists()


def test_a_characterized_plot_is_not_deleted_and_can_be_deactivated(auth_client):
    producer = ProducerFactory()
    client = auth_client(make_producer_owner(producer))
    plot = characterized_plot(FarmFactory(producer=producer))

    deleted = client.delete(f"/api/plots/{plot.pk}?expected_version=1")
    deactivated = client.patch(
        f"/api/plots/{plot.pk}", {"expected_version": 1, "is_active": False}, format="json"
    )

    assert deleted.status_code == 409
    assert deleted.data["code"] == "plot_has_records"
    assert deactivated.status_code == 200
    assert_characterization_kept(plot)


def test_a_plot_without_characterization_is_still_deleted(auth_client):
    producer = ProducerFactory()
    client = auth_client(make_producer_owner(producer))
    plot = PlotFactory(farm=FarmFactory(producer=producer))

    response = client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 204


def test_a_farm_with_a_characterized_plot_is_not_deleted(auth_client):
    producer = ProducerFactory()
    client = auth_client(make_producer_owner(producer))
    farm = FarmFactory(producer=producer)
    PlotFactory(farm=farm)
    plot = characterized_plot(farm)

    response = client.delete(f"/api/farms/{farm.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "farm_has_records"
    assert Plot.objects.filter(farm=farm).count() == 2
    assert_characterization_kept(plot)


def test_a_producer_with_a_characterized_plot_is_not_deleted(auth_client):
    # Sin abrir sesión con la cuenta del productor: una cuenta que ya entró también impide
    # eliminarlo, y aquí lo que se prueba es la ficha.
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    plot = characterized_plot(farm)
    association = auth_client(make_administrator())

    response = association.delete(f"/api/producers/{producer.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "producer_has_records"
    assert Producer.objects.filter(pk=producer.pk).exists()
    assert Farm.objects.filter(pk=farm.pk).exists()
    assert_characterization_kept(plot)


def test_the_same_producer_without_characterizations_is_deleted(auth_client):
    producer = ProducerFactory()
    PlotFactory(farm=FarmFactory(producer=producer))
    association = auth_client(make_administrator())

    response = association.delete(f"/api/producers/{producer.pk}?expected_version=1")

    assert response.status_code == 204
