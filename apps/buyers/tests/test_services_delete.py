import pytest

from apps.accounts.tests.factories import UserFactory
from apps.buyers.exceptions import BuyerHasRecords, BuyerNotFound, StaleBuyerVersion
from apps.buyers.models import Buyer, BuyerAuditEvent
from apps.buyers.services import delete_buyer, update_buyer
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def member(producer):
    return UserFactory(producer=producer)


def test_a_buyer_without_records_is_deleted_and_leaves_its_event(member, producer):
    buyer = BuyerFactory(producer=producer, buyer_type=Buyer.BuyerType.EXPORTER)
    buyer_id = buyer.pk

    delete_buyer(member, buyer_id, 1)

    assert not Buyer.objects.filter(pk=buyer_id).exists()
    event = BuyerAuditEvent.objects.get(action="deleted")
    assert (event.buyer, event.buyer_ref, event.buyer_type, event.actor) == (
        None,
        buyer_id,
        "exporter",
        member,
    )


def test_a_buyer_with_records_is_not_deleted(member, producer, buyer_usage_table):
    buyer = BuyerFactory(producer=producer)
    buyer_usage_table(buyer)

    with pytest.raises(BuyerHasRecords):
        delete_buyer(member, buyer.pk, 1)

    assert Buyer.objects.filter(pk=buyer.pk).exists()
    assert not BuyerAuditEvent.objects.filter(action="deleted").exists()


def test_a_stale_version_is_rejected(member, producer):
    buyer = BuyerFactory(producer=producer)
    update_buyer(member, buyer.pk, 1, {"name": "Otro nombre"})

    with pytest.raises(StaleBuyerVersion):
        delete_buyer(member, buyer.pk, 1)

    assert Buyer.objects.filter(pk=buyer.pk).exists()


def test_another_producers_buyer_is_not_found(member):
    foreign = BuyerFactory()

    with pytest.raises(BuyerNotFound):
        delete_buyer(member, foreign.pk, 1)

    assert Buyer.objects.filter(pk=foreign.pk).exists()
