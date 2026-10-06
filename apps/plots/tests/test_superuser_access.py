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


@pytest.fixture
def farm():
    return FarmFactory(**NEAR_SHAPES, producer=ProducerFactory(), area_hectares=Decimal("10"))


def test_the_technical_account_registers_a_plot_in_a_farm_of_any_producer(
    auth_client, superuser, farm
):
    response = auth_client(superuser).post("/api/plots", body(farm), format="json")

    assert response.status_code == 201
    plot = Plot.objects.get(pk=response.data["id"])
    assert plot.farm_id == farm.id
    assert PlotAuditEvent.objects.get(plot_ref=plot.id).actor_id == superuser.id


def test_the_technical_account_edits_and_lists_the_plots_of_any_farm(auth_client, superuser, farm):
    plot = PlotFactory(farm=farm, code="Lote 1")
    client = auth_client(superuser)

    listed = client.get(f"/api/plots?farm={farm.pk}")
    edited = client.patch(
        f"/api/plots/{plot.pk}",
        {"code": "Lote 2", "expected_version": plot.version},
        format="json",
    )

    assert [item["code"] for item in listed.data["results"]] == ["Lote 1"]
    assert edited.status_code == 200
    assert edited.data["code"] == "Lote 2"
