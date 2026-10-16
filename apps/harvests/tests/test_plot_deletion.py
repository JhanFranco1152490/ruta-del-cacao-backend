"""Una cosecha es un registro importante: impide eliminar su parcela, su finca y su productor.
Se prueba por las APIs de esas apps, que no saben nada de las cosechas."""

import pytest

from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.plots.models import Plot
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner_client(auth_client, producer):
    return auth_client(make_producer_owner(producer))


def harvested_plot(producer):
    plot = characterized_plot(farm=FarmFactory(producer=producer))
    HarvestFactory(plot=plot)
    return plot


def test_a_plot_with_harvests_is_not_deleted(owner_client, producer):
    plot = harvested_plot(producer)

    response = owner_client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "plot_has_records"
    assert Plot.objects.filter(pk=plot.pk).exists()


def test_a_farm_with_harvests_is_not_deleted(owner_client, producer):
    plot = harvested_plot(producer)

    response = owner_client.delete(f"/api/farms/{plot.farm_id}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "farm_has_records"
    assert Farm.objects.filter(pk=plot.farm_id).exists()


def test_a_producer_with_harvests_is_not_deleted(auth_client, producer):
    harvested_plot(producer)

    response = auth_client(make_administrator()).delete(
        f"/api/producers/{producer.pk}?expected_version=1"
    )

    assert response.status_code == 409
    assert response.data["code"] == "producer_has_records"
    assert Producer.objects.filter(pk=producer.pk).exists()
