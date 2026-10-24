import pytest

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.buyers.models import Buyer
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db

URL = "/api/buyers"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def buyer(producer):
    return BuyerFactory(producer=producer)


def delete_url(buyer, version=1) -> str:
    return f"{URL}/{buyer.pk}?expected_version={version}"


def test_delete_needs_a_session(anonymous_client, buyer):
    assert anonymous_client.delete(delete_url(buyer)).status_code == 401


def test_the_sales_manager_cannot_delete(auth_client, producer, buyer):
    manager = grant_role(
        UserFactory(producer=producer, farm=FarmFactory(producer=producer)),
        get_system_role(SALES_MANAGER),
    )

    assert auth_client(manager).delete(delete_url(buyer)).status_code == 403
    assert Buyer.objects.filter(pk=buyer.pk).exists()


def test_a_delegate_with_the_delete_permission_can_delete(auth_client, producer, buyer):
    delegate = make_delegate(producer, ["buyers.delete_buyer"], all_farms=True)

    assert auth_client(delegate).delete(delete_url(buyer)).status_code == 204


def test_the_producer_deletes_a_buyer_without_records(auth_client, owner, buyer):
    response = auth_client(owner).delete(delete_url(buyer))

    assert response.status_code == 204
    assert not Buyer.objects.filter(pk=buyer.pk).exists()


def test_a_buyer_with_records_answers_409(auth_client, owner, buyer, buyer_usage_table):
    buyer_usage_table(buyer)

    response = auth_client(owner).delete(delete_url(buyer))

    assert response.status_code == 409
    assert response.data["code"] == "buyer_has_records"
    assert Buyer.objects.filter(pk=buyer.pk).exists()


def test_the_version_is_required(auth_client, owner, buyer):
    response = auth_client(owner).delete(f"{URL}/{buyer.pk}")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_a_stale_version_answers_409_with_the_current_buyer(auth_client, owner, buyer):
    response = auth_client(owner).delete(delete_url(buyer, version=7))

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["id"] == str(buyer.pk)


def test_another_producers_buyer_is_not_found(auth_client, owner):
    foreign = BuyerFactory()

    assert auth_client(owner).delete(delete_url(foreign)).status_code == 404
