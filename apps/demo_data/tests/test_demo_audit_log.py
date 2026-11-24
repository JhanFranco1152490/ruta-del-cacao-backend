"""La bitácora con la semilla: lo más reciente primero, los cambios de demostración con su forma,
los filtros, quién no entra y que volver a sembrar no repite nada.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.common.serializers import full_name
from apps.demo_data.catalog import (
    DEMO_FOREMAN_EMAIL,
    DEMO_PRODUCER_EMAIL,
)
from apps.demo_data.seed import seed_demo_data

pytestmark = pytest.mark.django_db

URL = "/api/audit-log"


@pytest.fixture
def seeded():
    seed_demo_data()


def account(email):
    return User.objects.get(email=email)


def entries(auth_client, **params):
    response = auth_client(account(DEMO_PRODUCER_EMAIL)).get(URL, {"page_size": 100, **params})
    assert response.status_code == 200, response.data
    return response.data["results"]


def one(auth_client, record_type, action, **params):
    found = [
        entry
        for entry in entries(auth_client, record_type=record_type, **params)
        if entry["action"] == action
    ]
    assert found, (record_type, action)
    return found[0]


def changes_of(entry):
    return {change["field"]: change for change in entry["changes"]}


def test_the_log_comes_from_the_most_recent(auth_client, seeded):
    times = [entry["occurred_at"] for entry in entries(auth_client)]

    assert times == sorted(times, reverse=True)
    assert len(times) > 20


def test_the_harvest_correction_shows_the_collector_by_name(auth_client, seeded):
    entry = one(auth_client, "harvest", "updated")

    assert entry["actor"]["full_name"] == full_name(account(DEMO_FOREMAN_EMAIL))
    changes = changes_of(entry)
    assert {"green_weight_kg", "collector_id"} <= set(changes)
    names = {full_name(account(DEMO_FOREMAN_EMAIL)), full_name(account(DEMO_PRODUCER_EMAIL))}
    assert {changes["collector_id"]["before"], changes["collector_id"]["after"]} == names


def test_the_farm_edit_shows_its_area_and_details(auth_client, seeded):
    entry = one(auth_client, "farm", "updated")

    assert entry["record"]["label"].endswith("El Mirador")
    assert {"area_hectares", "details"} <= set(changes_of(entry))


def test_the_buyer_phone_is_hidden(auth_client, seeded):
    phone = changes_of(one(auth_client, "buyer", "updated"))["phone"]

    assert (phone["hidden"], phone["before"], phone["after"]) == ("personal", None, None)


def test_the_roles_of_the_foreman_are_shown_by_name(auth_client, seeded):
    # El capataz recibe el rol «Reportes de campo» en la semilla de reportes.
    foreman = full_name(account(DEMO_FOREMAN_EMAIL))
    [entry] = [
        entry
        for entry in entries(auth_client, record_type="account")
        if entry["action"] == "account_roles_changed" and entry["record"]["label"] == foreman
    ]

    roles = changes_of(entry)["roles"]
    assert roles["before"] == "Capataz/Operario"
    assert roles["after"] == "Capataz/Operario, Reportes de campo"


def test_the_filters_work_on_the_seed(auth_client, seeded):
    foreman = account(DEMO_FOREMAN_EMAIL)
    today = timezone.localdate().isoformat()

    by_foreman = entries(auth_client, actor=str(foreman.pk))
    harvests = entries(auth_client, record_type="harvest")
    of_today = entries(auth_client, **{"from": today, "to": today})

    assert by_foreman
    assert {entry["actor"]["id"] for entry in by_foreman} == {str(foreman.pk)}
    assert {entry["record_type"] for entry in harvests} == {"harvest"}
    assert of_today


def test_the_foreman_cannot_see_the_log(auth_client, seeded):
    response = auth_client(account(DEMO_FOREMAN_EMAIL)).get(URL)

    assert (response.status_code, response.data["code"]) == (403, "permission_denied")


def test_nothing_of_la_esperanza_reaches_another_producer(auth_client, seeded):
    other = (
        User.objects.exclude(producer=account(DEMO_PRODUCER_EMAIL).producer)
        .filter(producer__isnull=False, groups__role__code="producer")
        .first()
    )
    technical = auth_client(UserFactory(is_superuser=True))

    response = technical.get(URL, {"producer": str(other.producer_id), "page_size": 100})

    labels = {entry["record"]["label"] for entry in response.data["results"]}
    assert not any("La Esperanza" in label for label in labels)


def test_seeding_again_does_not_repeat_the_changes(auth_client, seeded):
    before = len(entries(auth_client, record_type="harvest"))

    seed_demo_data()

    assert len(entries(auth_client, record_type="harvest")) == before
    assert (
        len([e for e in entries(auth_client, record_type="buyer") if e["action"] == "updated"])
        == 1
    )
