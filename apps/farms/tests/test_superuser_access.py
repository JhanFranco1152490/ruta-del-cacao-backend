import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser():
    return UserFactory(is_superuser=True)


@pytest.fixture
def other_producers_farm():
    return FarmFactory(producer=ProducerFactory(), name="Alfa")


def test_the_technical_account_reads_the_detail_of_any_farm(
    auth_client, superuser, other_producers_farm
):
    response = auth_client(superuser).get(f"/api/farms/{other_producers_farm.pk}")

    assert response.status_code == 200
    assert response.data["name"] == "Alfa"


def test_the_technical_account_edits_a_farm_of_any_producer(
    auth_client, superuser, other_producers_farm
):
    response = auth_client(superuser).patch(
        f"/api/farms/{other_producers_farm.pk}",
        {"name": "Beta", "expected_version": other_producers_farm.version},
        format="json",
    )

    assert response.status_code == 200
    other_producers_farm.refresh_from_db()
    assert other_producers_farm.name == "Beta"
    event = FarmAuditEvent.objects.filter(farm_ref=other_producers_farm.pk).latest("occurred_at")
    assert event.actor_id == superuser.id


def test_the_technical_account_deactivates_a_farm_of_any_producer(
    auth_client, superuser, other_producers_farm
):
    response = auth_client(superuser).patch(
        f"/api/farms/{other_producers_farm.pk}",
        {"is_active": False, "expected_version": other_producers_farm.version},
        format="json",
    )

    assert response.status_code == 200
    other_producers_farm.refresh_from_db()
    assert other_producers_farm.is_active is False


def test_the_technical_account_deletes_a_farm_created_by_mistake(
    auth_client, superuser, other_producers_farm
):
    response = auth_client(superuser).delete(
        f"/api/farms/{other_producers_farm.pk}?expected_version={other_producers_farm.version}"
    )

    assert response.status_code == 204
    assert not Farm.objects.filter(pk=other_producers_farm.pk).exists()


def test_a_producer_still_cannot_reach_the_farm_of_another(auth_client, other_producers_farm):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).patch(
        f"/api/farms/{other_producers_farm.pk}",
        {"name": "Beta", "expected_version": other_producers_farm.version},
        format="json",
    )

    assert response.status_code == 404
