import pytest

from apps.accounts.tests.factories import UserFactory
from apps.inputs.models import AgriculturalInput, AgriculturalInputAuditEvent
from apps.inputs.producer_dependent import inputs_dependent
from apps.producers.exceptions import ProducerHasRecords
from apps.producers.models import Producer
from apps.producers.services import delete_producer
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


def test_inputs_without_records_are_not_important_and_are_counted():
    producer = ProducerFactory()
    AgriculturalInputFactory.create_batch(2, producer=producer)
    AgriculturalInputFactory()  # de otro productor

    assert inputs_dependent.important_record(producer) is None
    assert inputs_dependent.count(producer) == 2


def test_an_input_with_records_is_important(input_usage_table):
    producer = ProducerFactory()
    AgriculturalInputFactory(producer=producer)
    busy = AgriculturalInputFactory(producer=producer, name="En uso")
    input_usage_table(busy)

    assert "En uso" in inputs_dependent.important_record(producer)


def test_deleting_a_producer_removes_its_inputs_and_audits_each_one():
    producer = ProducerFactory()
    actor = UserFactory(is_superuser=True)
    mine = AgriculturalInputFactory.create_batch(2, producer=producer)
    other = AgriculturalInputFactory()

    delete_producer(actor, producer.pk, producer.version)

    assert not Producer.objects.filter(pk=producer.pk).exists()
    assert not AgriculturalInput.objects.filter(producer_id=producer.pk).exists()
    assert AgriculturalInput.objects.filter(pk=other.pk).exists()
    events = AgriculturalInputAuditEvent.objects.filter(
        input_ref__in=[item.pk for item in mine], action="deleted"
    )
    assert events.count() == 2
    assert {event.actor for event in events} == {actor}


def test_a_producer_whose_input_has_records_is_not_deleted(input_usage_table):
    producer = ProducerFactory()
    used = AgriculturalInputFactory(producer=producer)
    free = AgriculturalInputFactory(producer=producer)
    input_usage_table(used)

    with pytest.raises(ProducerHasRecords):
        delete_producer(UserFactory(is_superuser=True), producer.pk, producer.version)

    assert Producer.objects.filter(pk=producer.pk).exists()
    assert AgriculturalInput.objects.filter(pk__in=[used.pk, free.pk]).count() == 2
