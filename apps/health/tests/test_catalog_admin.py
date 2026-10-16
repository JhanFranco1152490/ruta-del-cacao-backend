import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.health.models import PestDisease
from apps.health.tests.factories import PestDiseaseFactory

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("plain_static_files", "empty_catalog"),
]

MANAGE = "health.manage_pestdisease"


def staff(*permissions):
    user = UserFactory(is_staff=True, permissions=list(permissions))
    client = Client()
    client.force_login(user)
    return client


def changelist_url():
    return reverse("admin:health_pestdisease_changelist")


def add_url():
    return reverse("admin:health_pestdisease_add")


def change_url(pest):
    return reverse("admin:health_pestdisease_change", args=[pest.pk])


def delete_url(pest):
    return reverse("admin:health_pestdisease_delete", args=[pest.pk])


def form(**overrides):
    return {
        "name": "Chinche verde",
        "kind": "pest",
        "scientific_name": "",
        "description": "Pica las mazorcas.",
        "is_active": "on",
        **overrides,
    }


def test_the_admin_needs_the_catalog_permission():
    assert staff().get(changelist_url()).status_code == 403
    assert staff(MANAGE).get(changelist_url()).status_code == 200


def test_adding_from_the_admin_normalizes_the_name():
    response = staff(MANAGE).post(add_url(), form(name=" Chinche – verde "))

    assert response.status_code == 302
    pest = PestDisease.objects.get()
    assert (pest.name, pest.normalized_name) == ("Chinche – verde", "chincheverde")
    assert pest.scientific_name is None


def test_the_admin_rejects_a_repeated_name_without_saving():
    PestDiseaseFactory(name="Chinche verde")

    response = staff(MANAGE).post(add_url(), form(name="chinche-verde"))

    assert response.status_code == 200
    assert "Ya existe una plaga o enfermedad con este nombre." in response.content.decode()
    assert PestDisease.objects.count() == 1


def test_editing_from_the_admin_deactivates_and_updates_the_search():
    pest = PestDiseaseFactory(name="Trips")

    staff(MANAGE).post(
        change_url(pest),
        form(name="Trips", scientific_name="Selenothrips rubrocinctus", is_active=""),
    )

    pest.refresh_from_db()
    assert pest.is_active is False
    assert pest.search_normalized == "trips|selenothripsrubrocinctus"


def test_one_registered_by_mistake_is_deleted_one_at_a_time():
    pest = PestDiseaseFactory()
    client = staff(MANAGE)

    response = client.post(delete_url(pest), {"post": "yes"})

    assert response.status_code == 302
    assert not PestDisease.objects.exists()
    assert "delete_selected" not in client.get(changelist_url()).content.decode()
