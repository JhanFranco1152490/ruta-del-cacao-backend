import uuid

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.common.csrf import CSRF_FAILED_DETAIL
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

FARM_PERMISSIONS = ["farms.view_farm", "farms.add_farm", "farms.change_farm"]
VALID_DATA = {
    "name": "La Esperanza",
    "department_id": "54",
    "municipality_id": "54001",
    "details": "Vereda El Pórtico, km 4",
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


def other_producer_farm(**kwargs):
    return FarmFactory(producer=ProducerFactory(), **kwargs)


# --- Acceso ------------------------------------------------------------------------------


def test_list_requires_authentication():
    response = APIClient().get("/api/farms")

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"


@pytest.mark.parametrize(
    "method, path_suffix, missing",
    [
        ("get", "", "farms.view_farm"),
        ("post", "", "farms.add_farm"),
        ("get", "/{id}", "farms.view_farm"),
        ("patch", "/{id}", "farms.change_farm"),
    ],
)
def test_each_action_requires_its_permission(auth_client, method, path_suffix, missing):
    user = UserFactory(
        producer=ProducerFactory(),
        permissions=[code for code in FARM_PERMISSIONS if code != missing],
    )
    farm = FarmFactory(producer=user.producer)
    path = "/api/farms" + path_suffix.format(id=farm.id)

    response = getattr(auth_client(user), method)(path, {}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_create_requires_csrf(anonymous_client, owner):
    anonymous_client.cookies["cacao_access"] = str(RefreshToken.for_user(owner).access_token)

    response = anonymous_client.post("/api/farms", VALID_DATA, format="json")

    assert response.status_code == 403
    assert response.data["detail"] == CSRF_FAILED_DETAIL
    assert not Farm.objects.exists()


def test_an_account_without_producer_cannot_create(auth_client):
    user = UserFactory(permissions=FARM_PERMISSIONS)

    response = auth_client(user).post("/api/farms", VALID_DATA, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


# --- Crear -------------------------------------------------------------------------------


def test_create_returns_the_farm_in_the_contract_shape(client, owner):
    client_id = uuid.uuid4()

    response = client.post("/api/farms", {**VALID_DATA, "id": str(client_id)}, format="json")

    assert response.status_code == 201
    assert response["Location"] == f"/api/farms/{client_id}"
    body = response.json()
    assert body == {
        "id": str(client_id),
        "name": "La Esperanza",
        "department": {"id": "54", "name": "Norte de Santander"},
        "municipality": {"id": "54001", "name": "Cúcuta"},
        "details": "Vereda El Pórtico, km 4",
        "area_hectares": "12.50",
        "altitude_masl": 950,
        "location": {"latitude": "7.8234567", "longitude": "-72.5123456"},
        "version": 1,
        "is_active": True,
        "created_at": body["created_at"],
        "updated_at": body["updated_at"],
    }
    assert Farm.objects.get().producer_id == owner.producer_id


def test_create_without_id_generates_one(client):
    response = client.post("/api/farms", VALID_DATA, format="json")

    assert response.status_code == 201
    assert Farm.objects.filter(pk=response.data["id"]).exists()


def test_details_is_optional(client):
    data = {key: value for key, value in VALID_DATA.items() if key != "details"}

    response = client.post("/api/farms", data, format="json")

    assert response.status_code == 201
    assert response.data["details"] == ""


def test_resending_the_same_farm_returns_200_without_duplicating(client):
    data = {**VALID_DATA, "id": str(uuid.uuid4())}
    first = client.post("/api/farms", data, format="json")

    again = client.post("/api/farms", data, format="json")

    assert again.status_code == 200
    assert again.data == first.data
    assert Farm.objects.count() == 1


def test_resending_an_id_with_other_content_is_a_conflict(client):
    data = {**VALID_DATA, "id": str(uuid.uuid4())}
    client.post("/api/farms", data, format="json")

    response = client.post("/api/farms", {**data, "altitude_masl": 1000}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "farm_id_conflict"


def test_the_producer_cannot_be_chosen_by_the_client(client):
    other = ProducerFactory()

    response = client.post(
        "/api/farms", {**VALID_DATA, "producer_id": str(other.id)}, format="json"
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]
    assert not Farm.objects.exists()


@pytest.mark.parametrize("missing", ["latitude", "longitude"])
def test_create_without_location_is_rejected(client, missing):
    data = {key: value for key, value in VALID_DATA.items() if key != missing}

    response = client.post("/api/farms", data, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "location_required"
    assert response.data["detail"] == "La georreferenciación es obligatoria."
    assert not Farm.objects.exists()


@pytest.mark.parametrize("missing", ["name", "department_id", "municipality_id"])
def test_create_reports_each_missing_required_field(client, missing):
    data = {key: value for key, value in VALID_DATA.items() if key != missing}

    response = client.post("/api/farms", data, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert missing in response.data["fields"]


@pytest.mark.parametrize(
    "field, value", [("latitude", "90.5"), ("latitude", "-91"), ("longitude", "180.1")]
)
def test_create_rejects_out_of_range_coordinates(client, field, value):
    response = client.post("/api/farms", {**VALID_DATA, field: value}, format="json")

    assert response.status_code == 422
    assert response.data["code"] == "invalid_coordinates"
    assert field in response.data["fields"]
    assert not Farm.objects.exists()


def test_create_rejects_a_non_positive_area(client):
    response = client.post("/api/farms", {**VALID_DATA, "area_hectares": "0"}, format="json")

    assert response.status_code == 400
    assert response.data["fields"]["area_hectares"] == ["El área debe ser mayor a 0."]


def test_create_reports_an_unknown_municipality_with_the_api_field_name(client):
    response = client.post("/api/farms", {**VALID_DATA, "municipality_id": "99999"}, format="json")

    assert response.status_code == 400
    assert "municipality_id" in response.data["fields"]


def test_create_rejects_a_duplicate_name(client):
    client.post("/api/farms", VALID_DATA, format="json")

    response = client.post("/api/farms", {**VALID_DATA, "name": " la esperanza "}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_farm_name"
    assert "name" in response.data["fields"]


# --- Consultar ---------------------------------------------------------------------------


def test_list_only_shows_own_farms_paginated_and_ordered(client, owner):
    FarmFactory(producer=owner.producer, name="Zapatoca")
    FarmFactory(producer=owner.producer, name="Arrayán")
    other_producer_farm(name="Ajena")

    response = client.get("/api/farms")

    assert response.status_code == 200
    assert response.data["count"] == 2
    assert [farm["name"] for farm in response.data["results"]] == ["Arrayán", "Zapatoca"]


def test_list_searches_and_paginates(client, owner):
    for number in range(3):
        FarmFactory(producer=owner.producer, name=f"Cacaotal {number}")
    FarmFactory(producer=owner.producer, name="Otra")

    response = client.get("/api/farms", {"search": "cacaotal", "page_size": 2})

    assert response.data["count"] == 3
    assert len(response.data["results"]) == 2
    assert response.data["next"] is not None


def test_list_query_count_does_not_grow_with_farms(client, owner):
    FarmFactory(producer=owner.producer)
    with CaptureQueriesContext(connection) as one:
        client.get("/api/farms")
    FarmFactory.create_batch(5, producer=owner.producer)

    with CaptureQueriesContext(connection) as many:
        client.get("/api/farms")

    assert len(many) == len(one)


def test_retrieve_returns_an_own_farm(client, owner):
    farm = FarmFactory(producer=owner.producer)

    response = client.get(f"/api/farms/{farm.id}")

    assert response.status_code == 200
    assert response.data["id"] == str(farm.id)


def test_retrieve_of_another_producer_farm_is_not_found(client):
    farm = other_producer_farm()

    response = client.get(f"/api/farms/{farm.id}")

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


# --- Editar ------------------------------------------------------------------------------


def create(client, **overrides):
    return client.post("/api/farms", {**VALID_DATA, **overrides}, format="json").data


def test_update_changes_the_farm_and_its_version(client):
    farm = create(client)

    response = client.patch(
        f"/api/farms/{farm['id']}",
        {"name": "El Porvenir", "latitude": "7.5", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["name"] == "El Porvenir"
    assert response.data["location"]["latitude"] == "7.5000000"
    assert response.data["version"] == 2
    event = FarmAuditEvent.objects.filter(action=FarmAuditEvent.Action.UPDATED).get()
    assert event.changed_fields == ["latitude", "name"]


def test_update_can_change_the_municipality(client):
    farm = create(client)

    response = client.patch(
        f"/api/farms/{farm['id']}",
        {"municipality_id": "54498", "expected_version": 1},
        format="json",
    )

    assert response.data["municipality"] == {"id": "54498", "name": "Ocaña"}


def test_update_with_a_stale_version_returns_the_current_farm(client):
    farm = create(client)
    client.patch(
        f"/api/farms/{farm['id']}", {"altitude_masl": 1000, "expected_version": 1}, format="json"
    )

    response = client.patch(
        f"/api/farms/{farm['id']}", {"altitude_masl": 1200, "expected_version": 1}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 2
    assert response.data["current"]["altitude_masl"] == 1000


def test_update_requires_expected_version(client):
    farm = create(client)

    response = client.patch(f"/api/farms/{farm['id']}", {"name": "Otra"}, format="json")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_update_requires_a_field_besides_the_version(client):
    farm = create(client)

    response = client.patch(f"/api/farms/{farm['id']}", {"expected_version": 1}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_update_cannot_remove_the_location(client):
    farm = create(client)

    response = client.patch(
        f"/api/farms/{farm['id']}", {"latitude": None, "expected_version": 1}, format="json"
    )

    assert response.status_code == 400
    assert "latitude" in response.data["fields"]


def test_update_rejects_a_duplicate_name(client):
    create(client, name="La Esperanza")
    other = create(client, name="El Porvenir")

    response = client.patch(
        f"/api/farms/{other['id']}", {"name": "LA ESPERANZA", "expected_version": 1}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_farm_name"


def test_update_of_another_producer_farm_is_not_found(client):
    farm = other_producer_farm(name="Ajena")

    response = client.patch(
        f"/api/farms/{farm.id}", {"name": "Mía", "expected_version": 1}, format="json"
    )

    assert response.status_code == 404
    farm.refresh_from_db()
    assert farm.name == "Ajena"


def test_deactivate_and_reactivate(client):
    farm = create(client)

    inactive = client.patch(
        f"/api/farms/{farm['id']}", {"is_active": False, "expected_version": 1}, format="json"
    )
    active = client.patch(
        f"/api/farms/{farm['id']}", {"is_active": True, "expected_version": 2}, format="json"
    )

    assert inactive.data["is_active"] is False
    assert active.data["is_active"] is True
    assert Farm.objects.filter(pk=farm["id"]).exists()
