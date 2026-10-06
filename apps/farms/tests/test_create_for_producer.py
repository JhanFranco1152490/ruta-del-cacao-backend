import uuid

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.farms.tests.test_api import VALID_DATA
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser():
    return UserFactory(is_superuser=True)


def create(client, producer_id=None, **overrides):
    data = {**VALID_DATA, **overrides}
    if producer_id is not None:
        data["producer_id"] = str(producer_id)
    return client.post("/api/farms", data, format="json")


def test_the_technical_account_registers_a_farm_for_the_producer_it_names(auth_client, superuser):
    producer = ProducerFactory()

    response = create(auth_client(superuser), producer.id)

    assert response.status_code == 201
    farm = Farm.objects.get(pk=response.data["id"])
    assert farm.producer_id == producer.id
    assert FarmAuditEvent.objects.get(farm_ref=farm.id).actor_id == superuser.id


def test_the_technical_account_must_name_a_producer(auth_client, superuser):
    response = create(auth_client(superuser))

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_a_producer_cannot_name_one_not_even_its_own(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    response = create(auth_client(owner), producer.id)

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_a_producer_without_a_name_registers_its_own_farm(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    response = create(auth_client(owner))

    assert response.status_code == 201
    assert Farm.objects.get(pk=response.data["id"]).producer_id == producer.id


def test_a_producer_that_does_not_exist_is_a_field_error(auth_client, superuser):
    response = create(auth_client(superuser), uuid.uuid4())

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]
    assert not Farm.objects.exists()


def test_an_inactive_producer_is_a_field_error(auth_client, superuser):
    response = create(auth_client(superuser), ProducerFactory(status="inactive").id)

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]
    assert not Farm.objects.exists()


def test_sending_the_same_farm_again_for_the_same_producer_is_not_a_duplicate(
    auth_client, superuser
):
    producer = ProducerFactory()
    farm_id = str(uuid.uuid4())
    client = auth_client(superuser)

    first = create(client, producer.id, id=farm_id)
    again = create(client, producer.id, id=farm_id)

    assert first.status_code == 201
    assert again.status_code == 200
    assert Farm.objects.count() == 1


def test_sending_the_same_farm_id_for_another_producer_is_a_conflict(auth_client, superuser):
    farm_id = str(uuid.uuid4())
    client = auth_client(superuser)
    create(client, ProducerFactory().id, id=farm_id)

    response = create(client, ProducerFactory().id, id=farm_id)

    assert response.status_code == 409
    assert response.data["code"] == "farm_id_conflict"


def test_a_farm_says_its_producer_in_the_list_and_in_the_detail(auth_client, superuser):
    producer = ProducerFactory(first_name="Ana", last_name="Prueba", member_code="PROD-000007")
    farm = FarmFactory(producer=producer)
    expected = {
        "id": str(producer.id),
        "member_code": "PROD-000007",
        "first_name": "Ana",
        "last_name": "Prueba",
    }
    client = auth_client(superuser)

    listed = client.get("/api/farms")
    detail = client.get(f"/api/farms/{farm.pk}")

    assert listed.data["results"][0]["producer"] == expected
    assert detail.data["producer"] == expected


def test_the_list_does_not_ask_for_the_producer_farm_by_farm(
    auth_client, superuser, django_assert_max_num_queries
):
    for _ in range(15):
        FarmFactory(producer=ProducerFactory())
    client = auth_client(superuser)

    with django_assert_max_num_queries(12):
        response = client.get("/api/farms")

    assert response.status_code == 200
    assert len(response.data["results"]) == 15
