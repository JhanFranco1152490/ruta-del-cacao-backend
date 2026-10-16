import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

PERMISSIONS = ["farms.view_farm", "farms.add_farm", "farms.change_farm"]
DATA = {
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
    return UserFactory(producer=ProducerFactory(), permissions=PERMISSIONS)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


def test_the_response_of_a_new_farm_carries_its_code(client):
    response = client.post("/api/farms", DATA, format="json")

    assert response.status_code == 201
    assert response.data["code"] == "F01"


def test_the_code_is_read_only(client, owner):
    farm = FarmFactory(producer=owner.producer)

    response = client.patch(
        f"/api/farms/{farm.pk}", {"code": "F99", "expected_version": 1}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    farm.refresh_from_db()
    assert farm.code == "F01"


def test_the_code_cannot_be_sent_when_creating(client):
    response = client.post("/api/farms", {**DATA, "code": "F05"}, format="json")

    assert response.status_code == 400


def test_the_list_and_the_detail_show_the_code(client, owner):
    farm = FarmFactory(producer=owner.producer)

    assert client.get(f"/api/farms/{farm.pk}").data["code"] == "F01"
    assert client.get("/api/farms").data["results"][0]["code"] == "F01"


@pytest.mark.parametrize("term", ["F02", "f2", "F 02"])
def test_search_finds_a_farm_by_its_code(client, owner, term):
    FarmFactory(producer=owner.producer, name="Alfa")
    FarmFactory(producer=owner.producer, name="Beta")
    FarmFactory(producer=owner.producer, name="Gamma")

    response = client.get("/api/farms", {"search": term})

    assert [farm["name"] for farm in response.data["results"]] == ["Beta"]


def test_search_still_finds_a_farm_by_its_name(client, owner):
    FarmFactory(producer=owner.producer, name="Alfa")
    FarmFactory(producer=owner.producer, name="Beta")

    response = client.get("/api/farms", {"search": "alf"})

    assert [farm["name"] for farm in response.data["results"]] == ["Alfa"]
