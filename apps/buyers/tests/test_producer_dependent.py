import pytest

from apps.accounts.tests.factories import UserFactory
from apps.buyers.models import Buyer, BuyerAuditEvent
from apps.buyers.producer_dependent import buyers_dependent
from apps.producers.exceptions import ProducerHasRecords
from apps.producers.models import Producer
from apps.producers.services import delete_producer
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db


def test_buyers_without_records_are_not_important_and_are_counted():
    producer = ProducerFactory()
    BuyerFactory.create_batch(2, producer=producer)
    BuyerFactory()  # de otro productor

    assert buyers_dependent.important_record(producer) is None
    assert buyers_dependent.count(producer) == 2


def test_a_buyer_with_records_is_important_without_naming_it(buyer_usage_table):
    producer = ProducerFactory()
    busy = BuyerFactory(producer=producer, name="Persona Natural De Ejemplo")
    buyer_usage_table(busy)

    reason = buyers_dependent.important_record(producer)

    assert reason
    # El comprador puede ser una persona: el motivo no lleva su nombre.
    assert "Persona Natural" not in reason


def test_deleting_a_producer_removes_its_buyers_and_audits_each_one():
    producer = ProducerFactory()
    actor = UserFactory(is_superuser=True)
    mine = BuyerFactory.create_batch(2, producer=producer)
    other = BuyerFactory()

    delete_producer(actor, producer.pk, producer.version)

    assert not Producer.objects.filter(pk=producer.pk).exists()
    assert not Buyer.objects.filter(producer_id=producer.pk).exists()
    assert Buyer.objects.filter(pk=other.pk).exists()
    events = BuyerAuditEvent.objects.filter(
        buyer_ref__in=[buyer.pk for buyer in mine], action="deleted"
    )
    assert events.count() == 2
    assert {event.actor for event in events} == {actor}


def test_a_producer_whose_buyer_has_records_is_not_deleted(buyer_usage_table):
    producer = ProducerFactory()
    used = BuyerFactory(producer=producer)
    free = BuyerFactory(producer=producer)
    buyer_usage_table(used)

    with pytest.raises(ProducerHasRecords):
        delete_producer(UserFactory(is_superuser=True), producer.pk, producer.version)

    assert Producer.objects.filter(pk=producer.pk).exists()
    assert Buyer.objects.filter(pk__in=[used.pk, free.pk]).count() == 2
