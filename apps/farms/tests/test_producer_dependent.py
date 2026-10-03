import pytest

from apps.accounts.tests.factories import UserFactory
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.producer_dependent import farms_dependent
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_farms_without_records_are_not_important_and_are_counted():
    producer = ProducerFactory()
    FarmFactory.create_batch(2, producer=producer)
    FarmFactory()  # de otro productor

    assert farms_dependent.important_record(producer) is None
    assert farms_dependent.count(producer) == 2


def test_a_farm_with_business_records_is_important(farm_dependent_model):
    producer = ProducerFactory()
    FarmFactory(producer=producer)
    busy = FarmFactory(producer=producer, name="Con registros")
    farm_dependent_model.objects.create(farm=busy)

    reason = farms_dependent.important_record(producer)

    assert "Con registros" in reason


def test_deleting_all_removes_only_that_producers_farms_and_audits_each_one():
    producer = ProducerFactory()
    actor = UserFactory()
    mine = FarmFactory.create_batch(2, producer=producer)
    other = FarmFactory()

    farms_dependent.delete_all(producer, actor)

    assert not Farm.objects.filter(producer=producer).exists()
    assert Farm.objects.filter(pk=other.pk).exists()
    events = FarmAuditEvent.objects.filter(
        farm_ref__in=[farm.pk for farm in mine], action=FarmAuditEvent.Action.DELETED
    )
    assert events.count() == 2
    assert {event.actor for event in events} == {actor}
