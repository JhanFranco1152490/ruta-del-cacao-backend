import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.farms.tests.test_api import VALID_DATA
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser():
    return UserFactory(is_superuser=True)


def under(producer) -> dict:
    return {"HTTP_X_ACTING_PRODUCER": str(producer.id)}


def test_a_farm_registered_under_a_producer_is_the_producers_and_audited_to_the_superuser(
    auth_client, superuser
):
    producer = ProducerFactory()

    response = auth_client(superuser).post(
        "/api/farms", VALID_DATA, format="json", **under(producer)
    )

    assert response.status_code == 201
    farm = Farm.objects.get(pk=response.data["id"])
    assert farm.producer_id == producer.id
    assert FarmAuditEvent.objects.get(farm_ref=farm.id).actor_id == superuser.id


def test_without_a_producer_the_superuser_cannot_register_a_farm(auth_client, superuser):
    response = auth_client(superuser).post("/api/farms", VALID_DATA, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_under_a_producer_the_superuser_reads_only_its_farms(auth_client, superuser):
    producer = ProducerFactory()
    FarmFactory(producer=producer, name="Alfa")
    FarmFactory(producer=ProducerFactory(), name="Beta")

    response = auth_client(superuser).get("/api/farms", **under(producer))

    assert [farm["name"] for farm in response.data["results"]] == ["Alfa"]


def test_without_a_producer_the_superuser_reads_every_farm(auth_client, superuser):
    FarmFactory(producer=ProducerFactory(), name="Alfa")
    FarmFactory(producer=ProducerFactory(), name="Beta")

    response = auth_client(superuser).get("/api/farms")

    assert sorted(farm["name"] for farm in response.data["results"]) == ["Alfa", "Beta"]


def test_a_farm_of_another_producer_is_not_reachable_under_the_chosen_one(auth_client, superuser):
    other_farm = FarmFactory(producer=ProducerFactory())

    response = auth_client(superuser).patch(
        f"/api/farms/{other_farm.pk}",
        {"name": "Otra", "expected_version": 1},
        format="json",
        **under(ProducerFactory()),
    )

    assert response.status_code == 404


def test_the_choice_does_not_leak_into_the_next_request(auth_client, superuser):
    producer = ProducerFactory()
    FarmFactory(producer=producer, name="Alfa")
    FarmFactory(producer=ProducerFactory(), name="Beta")
    client = auth_client(superuser)

    chosen = client.get("/api/farms", **under(producer))
    without = client.get("/api/farms")

    assert len(chosen.data["results"]) == 1
    assert len(without.data["results"]) == 2
