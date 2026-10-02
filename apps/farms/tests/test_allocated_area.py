import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.farms.exceptions import FarmAreaBelowPlots
from apps.farms.services import update_farm
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

FARM_PERMISSIONS = ["farms.view_farm", "farms.add_farm", "farms.change_farm"]


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory(), permissions=FARM_PERMISSIONS)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def farm(owner):
    """Finca de 10 ha con 6 ha asignadas a parcelas activas y 3 a una inactiva."""
    farm = FarmFactory(producer=owner.producer, area_hectares=Decimal("10.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("4.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("2.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("3.00"), is_active=False)
    return farm


# --- Área asignada -----------------------------------------------------------------------


def test_the_allocated_area_adds_only_the_active_plots(client, farm):
    listed = client.get("/api/farms").data["results"][0]
    detail = client.get(f"/api/farms/{farm.pk}").data

    assert listed["allocated_area_hectares"] == "6.00"
    assert detail["allocated_area_hectares"] == "6.00"


def test_a_farm_without_plots_has_nothing_allocated(client, owner):
    farm = FarmFactory(producer=owner.producer)

    assert client.get(f"/api/farms/{farm.pk}").data["allocated_area_hectares"] == "0.00"


def test_a_new_farm_has_nothing_allocated(client):
    body = {
        "name": "La Esperanza",
        "department_id": "54",
        "municipality_id": "54001",
        "area_hectares": "12.50",
        "altitude_masl": 950,
        "latitude": "7.8234567",
        "longitude": "-72.5123456",
    }

    response = client.post("/api/farms", body, format="json")

    assert response.status_code == 201
    assert response.data["allocated_area_hectares"] == "0.00"


def test_resending_an_existing_farm_returns_its_allocated_area(client, owner):
    body = {
        "id": str(uuid.uuid4()),
        "name": "La Esperanza",
        "department_id": "54",
        "municipality_id": "54001",
        "area_hectares": "12.50",
        "altitude_masl": 950,
        "latitude": "7.8234567",
        "longitude": "-72.5123456",
    }
    client.post("/api/farms", body, format="json")
    PlotFactory(farm_id=body["id"], area_hectares=Decimal("5.00"))

    response = client.post("/api/farms", body, format="json")

    assert response.status_code == 200
    assert response.data["allocated_area_hectares"] == "5.00"


def test_an_update_returns_the_allocated_area(client, farm):
    response = client.patch(
        f"/api/farms/{farm.pk}", {"altitude_masl": 1000, "expected_version": 1}, format="json"
    )

    assert response.status_code == 200
    assert response.data["allocated_area_hectares"] == "6.00"


def test_the_list_query_count_does_not_grow_with_farms_and_plots(client, owner):
    PlotFactory(farm=FarmFactory(producer=owner.producer))
    with CaptureQueriesContext(connection) as one:
        client.get("/api/farms")
    for _ in range(5):
        PlotFactory.create_batch(2, farm=FarmFactory(producer=owner.producer))

    with CaptureQueriesContext(connection) as many:
        client.get("/api/farms")

    assert len(many) == len(one)


# --- El área de la finca no baja de la asignada --------------------------------------------


def test_the_farm_area_cannot_go_below_its_active_plots(client, farm):
    response = client.patch(
        f"/api/farms/{farm.pk}", {"area_hectares": "5.00", "expected_version": 1}, format="json"
    )

    assert response.status_code == 422
    assert response.data["code"] == "farm_area_below_plots"
    assert response.data["detail"] == (
        "El área de la finca no puede ser menor que la de sus parcelas (6,00 ha)."
    )
    assert response.data["fields"] == {"area_hectares": [response.data["detail"]]}
    farm.refresh_from_db()
    assert (farm.area_hectares, farm.version) == (Decimal("10.00"), 1)


@pytest.mark.parametrize("area", ["8.00", "6.00"])
def test_the_farm_area_can_shrink_down_to_its_active_plots(owner, farm, area):
    updated = update_farm(owner, farm.pk, 1, {"area_hectares": Decimal(area)})

    assert updated.area_hectares == Decimal(area)


def test_other_changes_do_not_check_the_plots(owner, farm):
    # Una finca que ya quedó por debajo (datos anteriores a la regla) se puede seguir editando
    # en lo demás: la regla solo mira el área cuando cambia.
    farm.area_hectares = Decimal("1.00")
    farm.save()

    update_farm(owner, farm.pk, 1, {"altitude_masl": 1200})


def test_the_error_reports_the_allocated_area(owner, farm):
    with pytest.raises(FarmAreaBelowPlots) as error:
        update_farm(owner, farm.pk, 1, {"area_hectares": Decimal("5.99")})

    assert "6,00 ha" in error.value.detail
