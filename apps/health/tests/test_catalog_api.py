import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.health.models import PestDisease
from apps.health.tests.factories import PestDiseaseFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

URL = "/api/pests-diseases"
DUPLICATE_MESSAGE = "Ya existe una plaga o enfermedad con este nombre."


def item_url(pest) -> str:
    return f"{URL}/{pest.pk}"


def valid_body(**overrides) -> dict:
    return {
        "name": "Chinche verde",
        "kind": "pest",
        "scientific_name": "Nezara viridula",
        "description": "Pica las mazorcas y deja manchas oscuras.",
        **overrides,
    }


@pytest.fixture
def admin_client(auth_client):
    return auth_client(make_administrator())


# --- Listado ------------------------------------------------------------------------------------


def test_list_requires_a_session(api_client):
    assert api_client.get(URL).status_code == 401


def test_any_account_with_a_session_reads_the_catalog_sorted_by_name(auth_client):
    PestDiseaseFactory(name="Trips", kind="pest", scientific_name="Selenothrips rubrocinctus")
    PestDiseaseFactory(name="Monilia", kind="disease", description="Solo ataca la mazorca.")

    response = auth_client(UserFactory()).get(URL)

    assert response.status_code == 200
    assert [item["name"] for item in response.data["results"]] == ["Monilia", "Trips"]
    monilia = response.data["results"][0]
    assert set(monilia) == {
        "id",
        "name",
        "kind",
        "scientific_name",
        "description",
        "is_active",
        "suggested_sampling_unit",
        "suggested_control_method",
    }
    assert monilia["suggested_sampling_unit"] is None
    assert monilia["suggested_control_method"] is None
    assert (monilia["kind"], monilia["scientific_name"]) == ("disease", None)
    assert monilia["description"] == "Solo ataca la mazorca."


def test_the_catalog_is_not_paginated(auth_client):
    PestDiseaseFactory.create_batch(25)

    response = auth_client(UserFactory()).get(URL)

    assert set(response.data) == {"results"}
    assert len(response.data["results"]) == 25


@pytest.mark.parametrize(("is_active", "expected"), [("true", ["Trips"]), ("false", ["Monilia"])])
def test_list_filters_by_status(auth_client, is_active, expected):
    PestDiseaseFactory(name="Trips")
    PestDiseaseFactory(name="Monilia", is_active=False)

    response = auth_client(UserFactory()).get(URL, {"is_active": is_active})

    assert [item["name"] for item in response.data["results"]] == expected


def test_list_without_status_filter_brings_active_and_inactive(auth_client):
    PestDiseaseFactory(name="Trips")
    PestDiseaseFactory(name="Monilia", is_active=False)

    response = auth_client(UserFactory()).get(URL)

    assert len(response.data["results"]) == 2


@pytest.mark.parametrize("search", ["MONÍLIA", "moni", "roreri", "Moniliophthora  roreri"])
def test_search_compares_the_name_and_the_scientific_name_like_the_catalog(auth_client, search):
    PestDiseaseFactory(name="Monilia", scientific_name="Moniliophthora roreri")
    PestDiseaseFactory(name="Trips")

    response = auth_client(UserFactory()).get(URL, {"search": search})

    assert [item["name"] for item in response.data["results"]] == ["Monilia"]


# --- Registrar ----------------------------------------------------------------------------------


def test_the_association_registers_one_trimming_the_texts(admin_client):
    response = admin_client.post(
        URL,
        valid_body(name="  Chinche verde ", scientific_name=" Nezara viridula "),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["name"] == "Chinche verde"
    assert response.data["scientific_name"] == "Nezara viridula"
    assert response.data["is_active"] is True
    assert PestDisease.objects.get().normalized_name == "chincheverde"


def test_the_suggestions_are_stored_and_returned(admin_client):
    body = valid_body(suggested_sampling_unit="pods", suggested_control_method="fruit_removal")

    response = admin_client.post(URL, body, format="json")

    assert response.status_code == 201
    assert response.data["suggested_sampling_unit"] == "pods"
    assert response.data["suggested_control_method"] == "fruit_removal"
    stored = PestDisease.objects.get()
    assert (stored.suggested_sampling_unit, stored.suggested_control_method) == (
        "pods",
        "fruit_removal",
    )


@pytest.mark.parametrize(
    "field, value",
    [("suggested_sampling_unit", "leaves"), ("suggested_control_method", "burn")],
)
def test_a_suggestion_outside_the_options_is_a_400(admin_client, field, value):
    response = admin_client.post(URL, valid_body(**{field: value}), format="json")

    assert response.status_code == 400
    assert field in response.data["fields"]


def test_the_suggestions_can_be_changed_and_cleared(admin_client):
    pest = PestDiseaseFactory(
        suggested_sampling_unit="pods", suggested_control_method="fruit_removal"
    )

    changed = admin_client.patch(
        item_url(pest),
        {"suggested_sampling_unit": "trees", "suggested_control_method": None},
        format="json",
    )

    assert changed.status_code == 200
    assert changed.data["suggested_sampling_unit"] == "trees"
    assert changed.data["suggested_control_method"] is None


def test_editing_something_else_keeps_the_suggestions(admin_client):
    pest = PestDiseaseFactory(
        suggested_sampling_unit="pods", suggested_control_method="fruit_removal"
    )

    response = admin_client.patch(item_url(pest), {"description": "Otra."}, format="json")

    assert response.status_code == 200
    assert response.data["suggested_sampling_unit"] == "pods"
    assert response.data["suggested_control_method"] == "fruit_removal"


def test_the_scientific_name_is_optional(admin_client):
    body = valid_body()
    del body["scientific_name"]

    response = admin_client.post(URL, body, format="json")

    assert response.status_code == 201
    assert response.data["scientific_name"] is None


@pytest.mark.parametrize("scientific_name", [None, "", "   "])
def test_an_empty_scientific_name_is_stored_as_null(admin_client, scientific_name):
    response = admin_client.post(URL, valid_body(scientific_name=scientific_name), format="json")

    assert response.status_code == 201
    assert response.data["scientific_name"] is None


def test_a_producer_cannot_register_one(auth_client):
    producer_client = auth_client(make_producer_owner(ProducerFactory()))

    response = producer_client.post(URL, valid_body(), format="json")

    assert response.status_code == 403
    assert not PestDisease.objects.exists()


@pytest.mark.parametrize("repeated", ["chinche verde", "CHINCHE-VERDE", " Chínche  verde "])
def test_a_repeated_name_is_a_409_even_written_differently(admin_client, repeated):
    PestDiseaseFactory(name="Chinche verde", is_active=False)

    response = admin_client.post(URL, valid_body(name=repeated), format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_pest_disease_name"
    assert response.data["fields"] == {"name": [DUPLICATE_MESSAGE]}


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"name": "C"}, "name"),
        ({"name": "C" * 61}, "name"),
        ({"name": " - "}, "name"),
        ({"kind": "virus"}, "kind"),
        ({"scientific_name": "N" * 101}, "scientific_name"),
        ({"description": ""}, "description"),
        ({"description": "D" * 301}, "description"),
    ],
)
def test_invalid_values_are_a_400_on_their_field(admin_client, overrides, field):
    response = admin_client.post(URL, valid_body(**overrides), format="json")

    assert response.status_code == 400
    assert field in response.data["fields"]
    assert not PestDisease.objects.exists()


@pytest.mark.parametrize("missing", ["name", "kind", "description"])
def test_required_fields(admin_client, missing):
    body = valid_body()
    del body[missing]

    response = admin_client.post(URL, body, format="json")

    assert response.status_code == 400
    assert missing in response.data["fields"]


def test_unknown_fields_are_rejected(admin_client):
    response = admin_client.post(URL, valid_body(severity="alta"), format="json")

    assert response.status_code == 400
    assert "severity" in response.data["fields"]


# --- Editar, activar y desactivar ---------------------------------------------------------------


def test_the_association_edits_the_description(admin_client):
    pest = PestDiseaseFactory(name="Trips")

    response = admin_client.patch(
        item_url(pest), {"description": " Raspa el envés de las hojas. "}, format="json"
    )

    assert response.status_code == 200
    assert response.data["description"] == "Raspa el envés de las hojas."
    assert response.data["name"] == "Trips"


def test_renaming_updates_the_search(admin_client, auth_client):
    pest = PestDiseaseFactory(name="Trips")

    admin_client.patch(item_url(pest), {"name": "Trips del cacao"}, format="json")

    response = auth_client(UserFactory()).get(URL, {"search": "del cacao"})
    assert [item["name"] for item in response.data["results"]] == ["Trips del cacao"]


def test_the_scientific_name_is_removed_with_null(admin_client):
    pest = PestDiseaseFactory(scientific_name="Atta spp.")

    response = admin_client.patch(item_url(pest), {"scientific_name": None}, format="json")

    assert response.status_code == 200
    pest.refresh_from_db()
    assert pest.scientific_name is None
    assert pest.search_normalized == pest.normalized_name


def test_deactivating_and_activating(admin_client):
    pest = PestDiseaseFactory()

    off = admin_client.patch(item_url(pest), {"is_active": False}, format="json")
    on = admin_client.patch(item_url(pest), {"is_active": True}, format="json")

    assert (off.status_code, off.data["is_active"]) == (200, False)
    assert (on.status_code, on.data["is_active"]) == (200, True)


def test_renaming_to_another_existing_name_is_a_409(admin_client):
    PestDiseaseFactory(name="Monilia")
    pest = PestDiseaseFactory(name="Trips")

    response = admin_client.patch(item_url(pest), {"name": "MONILIA"}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_pest_disease_name"


def test_keeping_its_own_name_written_differently_is_not_a_repeat(admin_client):
    pest = PestDiseaseFactory(name="Mazorca negra")

    response = admin_client.patch(item_url(pest), {"name": "Mazorca Negra"}, format="json")

    assert response.status_code == 200
    assert response.data["name"] == "Mazorca Negra"


def test_an_empty_patch_is_a_400(admin_client):
    pest = PestDiseaseFactory()

    response = admin_client.patch(item_url(pest), {}, format="json")

    assert response.status_code == 400


def test_editing_one_that_does_not_exist_is_a_404(admin_client):
    response = admin_client.patch(
        f"{URL}/7f0c3e1a-0000-4000-8000-000000000000", {"is_active": False}, format="json"
    )

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


def test_a_producer_cannot_edit_the_catalog(auth_client):
    pest = PestDiseaseFactory()
    producer_client = auth_client(make_producer_owner(ProducerFactory()))

    response = producer_client.patch(item_url(pest), {"is_active": False}, format="json")

    assert response.status_code == 403
    pest.refresh_from_db()
    assert pest.is_active is True


def test_there_is_no_deletion_through_the_api(admin_client):
    pest = PestDiseaseFactory()

    response = admin_client.delete(item_url(pest))

    assert response.status_code == 405
    assert PestDisease.objects.filter(pk=pest.pk).exists()
