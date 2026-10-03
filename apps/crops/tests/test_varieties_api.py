import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.crops.models import CacaoVariety, CacaoVarietyAuditEvent
from apps.crops.tests.factories import CacaoVarietyFactory, PlotCharacterizationVarietyFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

URL = "/api/cacao-varieties"
DUPLICATE_MESSAGE = "Ya existe una variedad con este nombre."


def variety_url(variety) -> str:
    return f"{URL}/{variety.pk}"


def events(variety, action):
    return CacaoVarietyAuditEvent.objects.filter(variety_ref=variety.pk, action=action)


@pytest.fixture
def admin_client(auth_client):
    return auth_client(make_administrator())


# --- Listado ------------------------------------------------------------------------------------


def test_list_requires_a_session(api_client):
    response = api_client.get(URL)

    assert response.status_code == 401


def test_any_account_with_a_session_reads_the_catalog_sorted_by_name(auth_client):
    CacaoVarietyFactory(name="ICS-95", description="Procedencia: Trinidad.")
    CacaoVarietyFactory(name="CCN-51")

    response = auth_client(UserFactory()).get(URL)

    assert response.status_code == 200
    assert [item["name"] for item in response.data["results"]] == ["CCN-51", "ICS-95"]
    assert set(response.data["results"][1]) == {"id", "name", "description", "is_active"}
    assert response.data["results"][1]["description"] == "Procedencia: Trinidad."


def test_the_catalog_is_not_paginated(auth_client):
    CacaoVarietyFactory.create_batch(25)

    response = auth_client(UserFactory()).get(URL)

    assert set(response.data) == {"results"}
    assert len(response.data["results"]) == 25


@pytest.mark.parametrize(("is_active", "expected"), [("true", ["ICS-1"]), ("false", ["EET-8"])])
def test_list_filters_by_status(auth_client, is_active, expected):
    CacaoVarietyFactory(name="ICS-1")
    CacaoVarietyFactory(name="EET-8", is_active=False)

    response = auth_client(UserFactory()).get(URL, {"is_active": is_active})

    assert [item["name"] for item in response.data["results"]] == expected


def test_list_without_status_filter_brings_active_and_inactive(auth_client):
    CacaoVarietyFactory(name="ICS-1")
    CacaoVarietyFactory(name="EET-8", is_active=False)

    response = auth_client(UserFactory()).get(URL)

    assert len(response.data["results"]) == 2


@pytest.mark.parametrize("term", ["ccn 51", "CCN51", "ccn–51", "cn-5"])
def test_search_compares_names_as_the_catalog_does(auth_client, term):
    CacaoVarietyFactory(name="CCN-51")
    CacaoVarietyFactory(name="ICS-95")

    response = auth_client(UserFactory()).get(URL, {"search": term})

    assert [item["name"] for item in response.data["results"]] == ["CCN-51"]


def test_search_ignores_accents(auth_client):
    CacaoVarietyFactory(name="Híbrido o común (sin identificar)")

    response = auth_client(UserFactory()).get(URL, {"search": "HIBRIDO O COMUN"})

    assert len(response.data["results"]) == 1


def test_a_blank_search_lists_everything(auth_client):
    CacaoVarietyFactory.create_batch(2)

    response = auth_client(UserFactory()).get(URL, {"search": "  "})

    assert len(response.data["results"]) == 2


def test_a_malformed_status_filter_is_rejected(auth_client):
    response = auth_client(UserFactory()).get(URL, {"is_active": "quizas"})

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


# --- Registro -----------------------------------------------------------------------------------


def test_the_association_registers_a_variety(admin_client):
    response = admin_client.post(
        URL, {"name": "  ABC-12 ", "description": "Clon regional"}, format="json"
    )

    assert response.status_code == 201
    assert response.data["name"] == "ABC-12"
    assert response.data["description"] == "Clon regional"
    assert response.data["is_active"] is True
    variety = CacaoVariety.objects.get(pk=response.data["id"])
    assert variety.name_normalized == "abc12"


def test_the_description_is_optional(admin_client):
    response = admin_client.post(URL, {"name": "ABC-12"}, format="json")

    assert response.status_code == 201
    assert response.data["description"] == ""


def test_registering_leaves_a_created_event_with_its_actor(auth_client):
    admin = make_administrator()

    response = auth_client(admin).post(URL, {"name": "ABC-12"}, format="json")

    variety = CacaoVariety.objects.get(pk=response.data["id"])
    event = events(variety, CacaoVarietyAuditEvent.Action.CREATED).get()
    assert event.actor == admin
    assert event.variety_name == "ABC-12"


@pytest.mark.parametrize("repeated", ["CCN 51", "ccn51", "CCN–51", " ccn-51 "])
def test_a_repeated_name_is_rejected(admin_client, repeated):
    CacaoVarietyFactory(name="CCN-51")

    response = admin_client.post(URL, {"name": repeated}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_variety_name"
    assert response.data["fields"] == {"name": [DUPLICATE_MESSAGE]}
    assert CacaoVariety.objects.count() == 1
    assert not CacaoVarietyAuditEvent.objects.exists()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": " - "},
        {"name": "A" * 61},
        {"name": "ABC-12", "description": "D" * 201},
        {"name": "ABC-12", "is_active": False},
        {"name": "ABC-12", "id": "0b6f6b3c-1111-4a4a-8b8b-000000000000"},
    ],
    ids=[
        "missing",
        "empty",
        "blank",
        "only_dash",
        "too_long",
        "long_description",
        "status_on_create",
        "client_id",
    ],
)
def test_invalid_registrations_are_rejected(admin_client, body):
    response = admin_client.post(URL, body, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert not CacaoVariety.objects.exists()


def test_the_limits_of_name_and_description_are_accepted(admin_client):
    response = admin_client.post(URL, {"name": "A" * 60, "description": "D" * 200}, format="json")

    assert response.status_code == 201


def test_a_producer_cannot_register_varieties(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(URL, {"name": "ABC-12"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    assert not CacaoVariety.objects.exists()


def test_registering_requires_a_session(api_client):
    assert api_client.post(URL, {"name": "ABC-12"}, format="json").status_code == 401


# --- Edición y estado ---------------------------------------------------------------------------


def test_the_association_renames_a_variety(admin_client):
    variety = CacaoVarietyFactory(name="ABC-12")

    response = admin_client.patch(variety_url(variety), {"name": "ABC-13"}, format="json")

    assert response.status_code == 200
    assert response.data["name"] == "ABC-13"
    variety.refresh_from_db()
    assert variety.name_normalized == "abc13"
    event = events(variety, CacaoVarietyAuditEvent.Action.UPDATED).get()
    assert event.changed_fields == ["name"]
    assert event.variety_name == "ABC-13"


def test_rewriting_a_name_in_another_form_is_allowed(admin_client):
    variety = CacaoVarietyFactory(name="ABC 12")

    response = admin_client.patch(variety_url(variety), {"name": "ABC-12"}, format="json")

    assert response.status_code == 200
    assert response.data["name"] == "ABC-12"


def test_renaming_to_another_varietys_name_is_rejected(admin_client):
    CacaoVarietyFactory(name="CCN-51")
    variety = CacaoVarietyFactory(name="ABC-12")

    response = admin_client.patch(variety_url(variety), {"name": "ccn 51"}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_variety_name"
    variety.refresh_from_db()
    assert variety.name == "ABC-12"
    assert not CacaoVarietyAuditEvent.objects.exists()


def test_deactivating_leaves_a_status_event(admin_client):
    variety = CacaoVarietyFactory()

    response = admin_client.patch(variety_url(variety), {"is_active": False}, format="json")

    assert response.status_code == 200
    assert response.data["is_active"] is False
    event = events(variety, CacaoVarietyAuditEvent.Action.STATUS_CHANGED).get()
    assert event.changed_fields == ["is_active"]
    assert not events(variety, CacaoVarietyAuditEvent.Action.UPDATED).exists()


def test_reactivating_a_variety(admin_client):
    variety = CacaoVarietyFactory(is_active=False)

    response = admin_client.patch(variety_url(variety), {"is_active": True}, format="json")

    assert response.data["is_active"] is True


def test_editing_and_deactivating_at_once_leaves_both_events(admin_client):
    variety = CacaoVarietyFactory()

    admin_client.patch(
        variety_url(variety), {"description": "Otra", "is_active": False}, format="json"
    )

    assert events(variety, CacaoVarietyAuditEvent.Action.UPDATED).get().changed_fields == [
        "description"
    ]
    assert events(variety, CacaoVarietyAuditEvent.Action.STATUS_CHANGED).exists()


def test_a_patch_that_changes_nothing_leaves_no_event(admin_client):
    variety = CacaoVarietyFactory(name="ABC-12", description="Igual")

    response = admin_client.patch(
        variety_url(variety), {"name": " ABC-12 ", "description": "Igual"}, format="json"
    )

    assert response.status_code == 200
    assert not CacaoVarietyAuditEvent.objects.exists()


def test_deactivating_does_not_touch_the_characterizations_that_use_it(admin_client):
    row = PlotCharacterizationVarietyFactory()

    admin_client.patch(variety_url(row.variety), {"is_active": False}, format="json")

    row.refresh_from_db()
    assert row.tree_count == 600


@pytest.mark.parametrize(
    "body",
    [{}, {"name": ""}, {"description": "D" * 201}, {"name_normalized": "x"}, {"is_active": None}],
    ids=["empty", "empty_name", "long_description", "derived_field", "null_status"],
)
def test_invalid_edits_are_rejected(admin_client, body):
    variety = CacaoVarietyFactory(name="ABC-12")

    response = admin_client.patch(variety_url(variety), body, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    variety.refresh_from_db()
    assert variety.name == "ABC-12"


def test_editing_an_unknown_variety_is_not_found(admin_client):
    response = admin_client.patch(
        f"{URL}/0b6f6b3c-1111-4a4a-8b8b-000000000000", {"name": "X"}, format="json"
    )

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


def test_a_producer_cannot_edit_varieties(auth_client):
    variety = CacaoVarietyFactory()
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).patch(variety_url(variety), {"is_active": False}, format="json")

    assert response.status_code == 403
    variety.refresh_from_db()
    assert variety.is_active is True


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_the_api_offers_no_detail_replacement_or_deletion(admin_client, method):
    variety = CacaoVarietyFactory()

    response = getattr(admin_client, method)(variety_url(variety))

    assert response.status_code == 405
