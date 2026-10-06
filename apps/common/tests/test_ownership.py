import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.common.ownership import owner_filter, owns
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_the_technical_account_is_not_restricted_to_a_producer():
    superuser = UserFactory(is_superuser=True)

    assert owner_filter(superuser) == {}
    assert owner_filter(superuser, "farm__producer_id") == {}
    assert owns(superuser, ProducerFactory().id) is True


def test_a_producer_is_restricted_to_its_own():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    assert owner_filter(owner) == {"producer_id": producer.id}
    assert owner_filter(owner, "farm__producer_id") == {"farm__producer_id": producer.id}
    assert owns(owner, producer.id) is True
    assert owns(owner, ProducerFactory().id) is False


def test_an_account_without_a_producer_owns_nothing():
    assert owns(UserFactory(), ProducerFactory().id) is False
