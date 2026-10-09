import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

FARM_PERMISSIONS = ["farms.view_farm", "farms.add_farm", "farms.change_farm"]
NEW_FARM = {
    "name": "La Esperanza",
    "department_id": "54",
    "municipality_id": "54001",
    "area_hectares": "12.50",
    "altitude_masl": 950,
    "latitude": "7.8234567",
    "longitude": "-72.5123456",
}


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory(), permissions=FARM_PERMISSIONS)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def farm(owner):
    """Finca con dos parcelas activas y una inactiva."""
    farm = FarmFactory(producer=owner.producer, area_hectares=Decimal("10.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("2.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("2.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("1.00"), is_active=False)
    return farm


def test_counts_active_and_inactive_plots_in_the_list_and_the_detail(client, farm):
    listed = client.get("/api/farms").data["results"][0]
    detail = client.get(f"/api/farms/{farm.pk}").data

    assert listed["plot_count"] == 3
    assert detail["plot_count"] == 3


def test_counting_does_not_change_the_allocated_area(client, farm):
    # Contar y sumar recorren las mismas parcelas: ninguna de las dos cifras se multiplica.
    listed = client.get("/api/farms").data["results"][0]

    assert listed["allocated_area_hectares"] == "4.00"
    assert listed["plot_count"] == 3


def test_a_farm_without_plots_counts_zero(client, owner):
    farm = FarmFactory(producer=owner.producer)

    assert client.get(f"/api/farms/{farm.pk}").data["plot_count"] == 0


def test_a_new_farm_counts_zero(client):
    response = client.post("/api/farms", NEW_FARM, format="json")

    assert response.status_code == 201
    assert response.data["plot_count"] == 0


def test_resending_an_existing_farm_returns_its_count(client):
    body = {**NEW_FARM, "id": str(uuid.uuid4())}
    client.post("/api/farms", body, format="json")
    PlotFactory(farm_id=body["id"])

    response = client.post("/api/farms", body, format="json")

    assert response.status_code == 200
    assert response.data["plot_count"] == 1


def test_an_update_and_a_stale_version_return_the_count(client, farm):
    updated = client.patch(
        f"/api/farms/{farm.pk}", {"altitude_masl": 1000, "expected_version": 1}, format="json"
    )
    stale = client.patch(
        f"/api/farms/{farm.pk}", {"altitude_masl": 1100, "expected_version": 1}, format="json"
    )

    assert updated.data["plot_count"] == 3
    assert stale.status_code == 409
    assert stale.data["current"]["plot_count"] == 3


def test_the_association_gets_the_count_without_reading_plots(auth_client, farm):
    association = auth_client(make_administrator())

    assert association.get("/api/farms").data["results"][0]["plot_count"] == 3


def test_the_list_takes_the_same_queries_with_one_or_many_plots(client, farm):
    with CaptureQueriesContext(connection) as few:
        client.get("/api/farms")
    for _ in range(5):
        PlotFactory(farm=farm, area_hectares=Decimal("0.50"))

    with CaptureQueriesContext(connection) as many:
        response = client.get("/api/farms")

    assert response.data["results"][0]["plot_count"] == 8
    assert len(many) == len(few)
