from decimal import Decimal

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.inputs.models import AgriculturalInput, AgriculturalInputAuditEvent
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory, input_data

pytestmark = pytest.mark.django_db

URL = "/api/agricultural-inputs"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def foreman(producer):
    return grant_role(UserFactory(producer=producer), get_system_role(FOREMAN))


@pytest.fixture
def item(producer):
    return AgriculturalInputFactory(producer=producer, name="Urea", name_normalized="urea")


def detail(item) -> str:
    return f"{URL}/{item.pk}"


# --- Sesión y permisos ---


def test_every_route_needs_a_session(anonymous_client, item):
    assert anonymous_client.get(URL).status_code == 401
    assert anonymous_client.get(detail(item)).status_code == 401


def test_the_association_has_no_access_to_inputs(auth_client, item):
    client = auth_client(make_administrator())

    assert client.get(URL).status_code == 403
    assert client.post(URL, input_data(), format="json").status_code == 403


def test_a_delegate_that_only_views_cannot_write(auth_client, producer, item):
    client = auth_client(make_delegate(producer, ["inputs.view_agriculturalinput"]))

    assert client.get(URL).status_code == 200
    assert client.post(URL, input_data(name="Otro"), format="json").status_code == 403
    assert (
        client.patch(detail(item), {"name": "Otro", "expected_version": 1}, format="json")
    ).status_code == 403
    assert client.delete(f"{detail(item)}?expected_version=1").status_code == 403


def test_the_foreman_registers_and_edits_but_cannot_delete(auth_client, foreman, item):
    client = auth_client(foreman)

    assert client.post(URL, input_data(name="Cobre"), format="json").status_code == 201
    assert (
        client.patch(detail(item), {"name": "Urea 2", "expected_version": 1}, format="json")
    ).status_code == 200
    assert client.delete(f"{detail(item)}?expected_version=2").status_code == 403


def test_a_delegate_with_the_delete_permission_can_delete(auth_client, producer, item):
    delegate = make_delegate(
        producer, ["inputs.view_agriculturalinput", "inputs.delete_agriculturalinput"]
    )

    response = auth_client(delegate).delete(f"{detail(item)}?expected_version=1")

    assert response.status_code == 204


# --- Consulta ---


def test_list_returns_the_whole_catalog_ordered_by_name_without_pagination(
    auth_client, owner, producer
):
    AgriculturalInputFactory(producer=producer, name="Zinc", name_normalized="zinc")
    AgriculturalInputFactory(
        producer=producer, name="Abono", name_normalized="abono", is_active=False
    )
    AgriculturalInputFactory()

    response = auth_client(owner).get(URL)

    assert response.status_code == 200
    assert set(response.data) == {"results"}
    assert [row["name"] for row in response.data["results"]] == ["Abono", "Zinc"]
    assert "no-store" in response["Cache-Control"]


def test_the_representation_has_the_documented_shape(auth_client, owner, producer):
    bag = AgriculturalInputFactory(producer=producer, unit="bag", bag_weight_kg=Decimal("50"))

    row = auth_client(owner).get(detail(bag)).data

    assert set(row) == {
        "id",
        "producer",
        "name",
        "input_type",
        "unit",
        "bag_weight_kg",
        "is_active",
        "has_records",
        "version",
        "created_at",
        "updated_at",
    }
    assert row["bag_weight_kg"] == "50.00"
    assert row["has_records"] is False
    assert row["producer"] == {
        "id": str(producer.pk),
        "member_code": producer.member_code,
        "first_name": producer.first_name,
        "last_name": producer.last_name,
    }


def test_has_records_is_true_for_a_used_input(auth_client, owner, producer, input_usage_table):
    used = AgriculturalInputFactory(producer=producer)
    input_usage_table(used)

    assert auth_client(owner).get(detail(used)).data["has_records"] is True


def test_an_account_without_a_producer_but_with_the_permission_sees_an_empty_catalog(
    auth_client, item
):
    stray = grant_role(UserFactory(), get_system_role(FOREMAN))

    client = auth_client(stray)
    assert client.get(URL).data["results"] == []
    assert client.post(URL, input_data(), format="json").status_code == 403


def test_another_producers_input_is_not_found(auth_client, owner):
    foreign = AgriculturalInputFactory()
    client = auth_client(owner)

    assert client.get(detail(foreign)).status_code == 404
    assert (
        client.patch(detail(foreign), {"name": "Xx", "expected_version": 1}, format="json")
    ).status_code == 404
    assert client.delete(f"{detail(foreign)}?expected_version=1").status_code == 404
    assert AgriculturalInput.objects.filter(pk=foreign.pk, name=foreign.name).exists()


def test_an_id_that_is_not_a_uuid_is_not_found(auth_client, owner):
    assert auth_client(owner).get(f"{URL}/no-es-un-id").status_code == 404


def test_the_producer_filter_is_ignored_for_regular_accounts(auth_client, owner, item):
    other = ProducerFactory()
    AgriculturalInputFactory(producer=other)

    response = auth_client(owner).get(URL, {"producer": str(other.pk)})

    assert [row["id"] for row in response.data["results"]] == [str(item.pk)]


def test_a_malformed_producer_filter_is_a_validation_error(auth_client, owner):
    response = auth_client(owner).get(URL, {"producer": "x"})

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


# --- Alta ---


def test_create_returns_201_with_location_and_the_input(auth_client, owner, producer):
    response = auth_client(owner).post(
        URL, input_data(unit="bag", bag_weight_kg="50"), format="json"
    )

    assert response.status_code == 201
    created = AgriculturalInput.objects.get()
    assert response["Location"] == detail(created)
    assert response.data["bag_weight_kg"] == "50.00"
    assert (response.data["version"], response.data["is_active"]) == (1, True)
    assert created.producer_id == producer.pk
    assert AgriculturalInputAuditEvent.objects.get().action == "created"


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"name": None}, "name"),
        ({"name": ""}, "name"),
        ({"name": "x"}, "name"),
        ({"name": "x" * 81}, "name"),
        ({"name": " - "}, "name"),
        ({"input_type": None}, "input_type"),
        ({"input_type": "herbicide"}, "input_type"),
        ({"unit": None}, "unit"),
        ({"unit": "gallon"}, "unit"),
        ({"unit": "bag"}, "bag_weight_kg"),
        ({"unit": "bag", "bag_weight_kg": "0.5"}, "bag_weight_kg"),
        ({"unit": "bag", "bag_weight_kg": "100.5"}, "bag_weight_kg"),
        ({"unit": "kg", "bag_weight_kg": "50"}, "bag_weight_kg"),
        ({"version": 3}, "version"),
        ({"is_active": False}, "is_active"),
        ({"producer_id": "6f1a7e0e-0000-4000-8000-000000000000"}, "producer_id"),
    ],
)
def test_create_rejects_invalid_data_by_field(auth_client, owner, changes, field):
    body = {**input_data(), **changes}
    body = {key: value for key, value in body.items() if value is not None}

    response = auth_client(owner).post(URL, body, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert field in response.data["fields"]
    assert not AgriculturalInput.objects.exists()


def test_create_with_a_duplicate_answers_409_with_the_existing_one(auth_client, owner, item):
    response = auth_client(owner).post(URL, input_data(name="UREA"), format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_input"
    assert response.data["existing"] == {
        "id": str(item.pk),
        "name": "Urea",
        "input_type": "fertilizer",
        "is_active": True,
    }
    assert "name" in response.data["fields"]


def test_the_technical_account_creates_for_a_named_producer(auth_client, producer):
    client = auth_client(UserFactory(is_superuser=True))

    response = client.post(URL, input_data(producer_id=str(producer.pk)), format="json")

    assert response.status_code == 201
    assert response.data["producer"]["id"] == str(producer.pk)


def test_the_technical_account_must_name_the_producer(auth_client):
    response = auth_client(UserFactory(is_superuser=True)).post(URL, input_data(), format="json")

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_the_technical_account_cannot_create_for_an_inactive_producer(auth_client, producer):
    Producer.objects.filter(pk=producer.pk).update(status=Producer.Status.INACTIVE)

    response = auth_client(UserFactory(is_superuser=True)).post(
        URL, input_data(producer_id=str(producer.pk)), format="json"
    )

    assert response.status_code == 422
    assert response.data["code"] == "producer_inactive"


def test_the_technical_account_reads_and_filters_every_catalog(auth_client, producer, item):
    other = AgriculturalInputFactory()
    client = auth_client(UserFactory(is_superuser=True))

    assert len(client.get(URL).data["results"]) == 2
    filtered = client.get(URL, {"producer": str(other.producer_id)})
    assert [row["id"] for row in filtered.data["results"]] == [str(other.pk)]


# --- Edición ---


def test_patch_updates_and_returns_the_new_version(auth_client, owner, item):
    response = auth_client(owner).patch(
        detail(item), {"name": "Urea 46 %", "expected_version": 1}, format="json"
    )

    assert response.status_code == 200
    assert (response.data["name"], response.data["version"]) == ("Urea 46 %", 2)


def test_patch_can_deactivate_and_reactivate(auth_client, owner, item):
    client = auth_client(owner)

    off = client.patch(detail(item), {"is_active": False, "expected_version": 1}, format="json")
    on = client.patch(detail(item), {"is_active": True, "expected_version": 2}, format="json")

    assert (off.data["is_active"], on.data["is_active"]) == (False, True)


@pytest.mark.parametrize(
    "body, field",
    [
        ({"name": "Urea 2"}, "expected_version"),
        ({"expected_version": 1}, None),
        ({"name": "", "expected_version": 1}, "name"),
        ({"unit": "bag", "expected_version": 1}, "bag_weight_kg"),
        ({"producer_id": "x", "name": "Urea 2", "expected_version": 1}, "producer_id"),
        ({"version": 1, "name": "Urea 2", "expected_version": 1}, "version"),
    ],
)
def test_patch_rejects_bad_bodies(auth_client, owner, item, body, field):
    response = auth_client(owner).patch(detail(item), body, format="json")

    assert response.status_code == 400
    if field:
        assert field in response.data["fields"]


def test_patch_with_an_old_version_answers_409_with_the_current_input(auth_client, owner, item):
    client = auth_client(owner)
    client.patch(detail(item), {"name": "Urea 2", "expected_version": 1}, format="json")

    response = client.patch(detail(item), {"name": "Urea 3", "expected_version": 1}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["name"] == "Urea 2"
    assert response.data["current"]["version"] == 2


def test_retrying_an_applied_patch_answers_200_without_a_new_version(auth_client, owner, item):
    client = auth_client(owner)
    body = {"name": "Urea 2", "expected_version": 1}
    client.patch(detail(item), body, format="json")

    response = client.patch(detail(item), body, format="json")

    assert response.status_code == 200
    assert response.data["version"] == 2
    assert AgriculturalInputAuditEvent.objects.filter(action="updated").count() == 1


def test_patch_with_the_name_of_another_input_answers_409(auth_client, owner, producer, item):
    AgriculturalInputFactory(producer=producer, name="Cal", name_normalized="cal")

    response = auth_client(owner).patch(
        detail(item), {"name": "cal", "expected_version": 1}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_input"
    assert response.data["existing"]["name"] == "Cal"


def test_patch_cannot_change_the_unit_of_a_used_input(
    auth_client, owner, producer, input_usage_table
):
    used = AgriculturalInputFactory(producer=producer)
    input_usage_table(used)

    response = auth_client(owner).patch(
        detail(used), {"unit": "l", "expected_version": 1}, format="json"
    )

    assert response.status_code == 422
    assert response.data["code"] == "input_unit_locked"
    assert "unit" in response.data["fields"]


# --- Baja ---


def test_delete_answers_204_and_leaves_the_deleted_event(auth_client, owner, item):
    response = auth_client(owner).delete(f"{detail(item)}?expected_version=1")

    assert response.status_code == 204
    assert not AgriculturalInput.objects.exists()
    event = AgriculturalInputAuditEvent.objects.get(action="deleted")
    assert (event.input_ref, event.input_name) == (item.pk, "Urea")


def test_delete_needs_the_expected_version(auth_client, owner, item):
    response = auth_client(owner).delete(detail(item))

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]
    assert AgriculturalInput.objects.exists()


def test_delete_with_an_old_version_answers_409_with_the_current_input(auth_client, owner, item):
    client = auth_client(owner)
    client.patch(detail(item), {"name": "Urea 2", "expected_version": 1}, format="json")

    response = client.delete(f"{detail(item)}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 2


def test_delete_of_a_used_input_answers_409(auth_client, owner, producer, input_usage_table):
    used = AgriculturalInputFactory(producer=producer)
    input_usage_table(used)

    response = auth_client(owner).delete(f"{detail(used)}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "input_has_records"
    assert AgriculturalInput.objects.filter(pk=used.pk).exists()
