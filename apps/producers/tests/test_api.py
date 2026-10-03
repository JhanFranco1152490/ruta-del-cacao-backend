import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.common.csrf import CSRF_FAILED_DETAIL
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

VALID_DATA = {
    "document_type": "CC",
    "identity_document": "12345678",
    "first_name": "Ana",
    "last_name": "Gomez",
    "municipality_code": "54001",
    "joined_on": "2026-09-21",
    "email": "ana@example.com",
}


# --- Acceso ---


def test_list_requires_authentication():
    response = APIClient().get("/api/producers")

    assert response.status_code == 401
    assert response.data["code"] == "not_authenticated"


def test_list_requires_view_permission(client_with):
    response = client_with("producers.create").get("/api/producers")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_create_requires_create_permission(client_with):
    response = client_with("producers.view").post("/api/producers", VALID_DATA, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_retrieve_requires_view_permission(client_with):
    producer = ProducerFactory()

    response = client_with("producers.create").get(f"/api/producers/{producer.id}")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_partial_update_requires_update_permission(client_with):
    producer = ProducerFactory(first_name="Ana")

    response = client_with("producers.view").patch(
        f"/api/producers/{producer.id}",
        {"first_name": "Beatriz", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    producer.refresh_from_db()
    assert (producer.first_name, producer.version) == ("Ana", 1)


def test_create_requires_csrf(anonymous_client):
    user = UserFactory(permissions=["producers.create"])
    anonymous_client.cookies["cacao_access"] = str(RefreshToken.for_user(user).access_token)

    response = anonymous_client.post("/api/producers", VALID_DATA, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert response.data["detail"] == CSRF_FAILED_DETAIL
    assert not Producer.objects.exists()


def test_unsupported_methods_are_not_allowed(admin_client):
    # `DELETE` sí existe (solo para un productor creado por error): ver test_delete_api.py.
    producer = ProducerFactory()

    response = admin_client.put(f"/api/producers/{producer.id}", {}, format="json")

    assert response.status_code == 405
    assert response.data["code"] == "method_not_allowed"


# --- Listado ---


def test_list_is_paginated_without_contact_data(admin_client):
    ProducerFactory(phone="3001234567", email="ana@example.com")

    response = admin_client.get("/api/producers")

    assert response.status_code == 200
    assert set(response.data) == {"count", "next", "previous", "results"}
    assert response.data["count"] == 1
    assert "phone" not in response.data["results"][0]
    assert "email" not in response.data["results"][0]
    assert "no-store" in response["Cache-Control"]


def test_list_filters_by_municipality_and_paginates(admin_client):
    ProducerFactory(last_name="Alvarez", municipality_code="54001")
    ProducerFactory(last_name="Zuluaga", municipality_code="54001")
    ProducerFactory(last_name="Perez", municipality_code="54003")

    response = admin_client.get(
        "/api/producers", {"municipality_code": "54001", "page": 1, "page_size": 1}
    )

    assert response.data["count"] == 2
    assert response.data["results"][0]["last_name"] == "Alvarez"
    assert response.data["next"] is not None


def test_list_searches_and_filters_by_status(admin_client):
    target = ProducerFactory(status=Producer.Status.INACTIVE)
    ProducerFactory()

    response = admin_client.get(f"/api/producers?search={target.member_code}&status=inactive")

    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == str(target.id)


def test_list_search_combines_words(admin_client):
    ProducerFactory(first_name="Ana", last_name="Perez")
    ProducerFactory(first_name="Ana", last_name="Gomez")

    response = admin_client.get("/api/producers", {"search": "ana perez"})

    assert response.data["count"] == 1


def test_list_rejects_an_unknown_status(admin_client):
    response = admin_client.get("/api/producers?status=archived")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_list_page_size_is_capped_at_one_hundred(admin_client):
    ProducerFactory.create_batch(101)

    response = admin_client.get("/api/producers", {"page_size": 500})

    assert response.data["count"] == 101
    assert len(response.data["results"]) == 100


@pytest.mark.parametrize("page", ["0", "99"])
def test_list_page_out_of_range_is_not_found(admin_client, page):
    ProducerFactory()

    response = admin_client.get(f"/api/producers?page={page}")

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


# --- Detalle ---


def test_detail_returns_the_full_record(admin_client):
    producer = ProducerFactory(email="ana@example.com")

    response = admin_client.get(f"/api/producers/{producer.id}")

    assert response.status_code == 200
    assert response.data["email"] == "ana@example.com"
    assert response.data["version"] == 1


def test_detail_of_unknown_producer_is_not_found(admin_client):
    response = admin_client.get("/api/producers/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.data == {
        "detail": "El productor no existe.",
        "code": "not_found",
        "fields": {},
    }


# --- Alta ---


def test_create_assigns_code_version_and_location(admin_client):
    response = admin_client.post("/api/producers", VALID_DATA, format="json")

    assert response.status_code == 201
    assert response.data["member_code"].startswith("PROD-")
    assert response.data["status"] == "active"
    assert response.data["version"] == 1
    assert response["Location"] == f"/api/producers/{response.data['id']}"


def test_create_normalizes_contact_and_names(admin_client):
    response = admin_client.post(
        "/api/producers",
        {**VALID_DATA, "first_name": " Ana ", "email": " ANA@EXAMPLE.COM ", "phone": ""},
        format="json",
    )

    assert response.data["first_name"] == "Ana"
    assert response.data["email"] == "ana@example.com"
    assert response.data["phone"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "no-es-correo"),
        ("joined_on", "2999-01-01"),
        ("phone", "300 123 4567"),
        ("identity_document", "12345"),
        ("identity_document", "12.345-ABC"),
        ("municipality_code", "05001"),
        ("document_type", "PASSPORT"),
        ("first_name", "   "),
    ],
)
def test_create_rejects_invalid_fields(admin_client, field, value):
    response = admin_client.post("/api/producers", {**VALID_DATA, field: value}, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert field in response.data["fields"]


def test_create_accepts_null_optional_phone(admin_client):
    response = admin_client.post("/api/producers", {**VALID_DATA, "phone": None}, format="json")

    assert response.status_code == 201
    assert response.data["phone"] is None


@pytest.mark.parametrize("data", [{}, {"email": None}])
def test_create_requires_email(admin_client, data):
    # HU-03 crea la cuenta Productor con este correo en la misma operación (ver
    # apps/producers/tests/test_account_link.py); sin correo no hay cuenta posible.
    body = {**{k: v for k, v in VALID_DATA.items() if k != "email"}, **data}

    response = admin_client.post("/api/producers", body, format="json")

    assert response.status_code == 400
    assert "email" in response.data["fields"]


def test_create_rejects_unknown_and_read_only_fields(admin_client):
    response = admin_client.post(
        "/api/producers", {**VALID_DATA, "unexpected": "x", "status": "inactive"}, format="json"
    )

    assert response.status_code == 400
    assert set(response.data["fields"]) == {"unexpected", "status"}


def test_duplicate_document_points_to_the_existing_record(admin_client):
    existing = ProducerFactory(identity_document="12345678")

    response = admin_client.post("/api/producers", VALID_DATA, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_document"
    assert response.data["existing_producer_id"] == str(existing.id)
    assert "identity_document" in response.data["fields"]


def test_duplicate_document_hides_the_record_without_view_permission(client_with):
    ProducerFactory(identity_document="12345678")

    response = client_with("producers.create").post("/api/producers", VALID_DATA, format="json")

    assert response.status_code == 409
    assert "existing_producer_id" not in response.data


# --- Edición ---


def test_update_with_current_version_increments_it(admin_client):
    producer = ProducerFactory()

    response = admin_client.patch(
        f"/api/producers/{producer.id}",
        {"first_name": "Beatriz", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["first_name"] == "Beatriz"
    assert response.data["version"] == 2


def test_update_with_stale_version_is_a_conflict(admin_client):
    producer = ProducerFactory()

    response = admin_client.patch(
        f"/api/producers/{producer.id}",
        {"first_name": "Beatriz", "expected_version": 2},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"


def test_update_to_a_duplicate_document_is_a_conflict(admin_client):
    ProducerFactory(identity_document="87654321")
    producer = ProducerFactory()

    response = admin_client.patch(
        f"/api/producers/{producer.id}",
        {"identity_document": "87654321", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_document"


@pytest.mark.parametrize("field", ["status", "member_code", "version", "id"])
def test_update_rejects_read_only_fields(admin_client, field):
    producer = ProducerFactory()

    response = admin_client.patch(
        f"/api/producers/{producer.id}", {field: "x", "expected_version": 1}, format="json"
    )

    assert response.status_code == 400
    assert field in response.data["fields"]


def test_update_needs_a_field_and_the_expected_version(admin_client):
    producer = ProducerFactory()
    url = f"/api/producers/{producer.id}"

    only_version = admin_client.patch(url, {"expected_version": 1}, format="json")
    no_version = admin_client.patch(url, {"first_name": "Bea"}, format="json")

    assert only_version.status_code == 400
    assert no_version.status_code == 400
    assert "expected_version" in no_version.data["fields"]


# --- Estado ---


def test_status_deactivates_and_reactivates(admin_client):
    producer = ProducerFactory()
    url = f"/api/producers/{producer.id}/status"

    inactive = admin_client.patch(
        url, {"status": "inactive", "expected_version": 1}, format="json"
    )
    active = admin_client.patch(url, {"status": "active", "expected_version": 2}, format="json")

    assert inactive.data["status"] == "inactive"
    assert active.data["status"] == "active"
    assert active.data["version"] == 3


def test_status_requires_its_own_permission(client_with):
    producer = ProducerFactory()

    response = client_with("producers.update").patch(
        f"/api/producers/{producer.id}/status",
        {"status": "inactive", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 403
