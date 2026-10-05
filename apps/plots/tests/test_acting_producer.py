from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.tests.factories import NEAR_SHAPES, PlotFactory
from apps.plots.tests.test_api import body
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser():
    return UserFactory(is_superuser=True)


def make_farm(producer):
    return FarmFactory(**NEAR_SHAPES, producer=producer, area_hectares=Decimal("10"))


def test_a_plot_registered_under_a_producer_is_audited_to_the_superuser(auth_client, superuser):
    farm = make_farm(ProducerFactory())

    response = auth_client(superuser).post(
        "/api/plots",
        body(farm),
        format="json",
        HTTP_X_ACTING_PRODUCER=str(farm.producer_id),
    )

    assert response.status_code == 201
    plot = Plot.objects.get(pk=response.data["id"])
    assert plot.farm_id == farm.id
    assert PlotAuditEvent.objects.get(plot_ref=plot.id).actor_id == superuser.id


def test_without_a_producer_the_superuser_cannot_register_a_plot(auth_client, superuser):
    farm = make_farm(ProducerFactory())

    response = auth_client(superuser).post("/api/plots", body(farm), format="json")

    assert response.status_code == 404
    assert not Plot.objects.exists()


def test_the_plots_of_another_producer_are_not_listed_under_the_chosen_one(auth_client, superuser):
    chosen = ProducerFactory()
    PlotFactory(farm=make_farm(chosen), code="Propia")
    PlotFactory(farm=make_farm(ProducerFactory()), code="Ajena")

    response = auth_client(superuser).get("/api/plots", HTTP_X_ACTING_PRODUCER=str(chosen.id))

    assert [plot["code"] for plot in response.data["results"]] == ["Propia"]
