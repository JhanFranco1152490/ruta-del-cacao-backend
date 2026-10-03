from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.models import AssociationAccess, User
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import enable_association_access, make_administrator
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.producers.exceptions import ProducerHasRecords, ProducerNotFound, StaleVersion
from apps.producers.models import Producer, ProducerAuditEvent
from apps.producers.services import create_producer, delete_producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor():
    return make_administrator()


def _sign_in(user):
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])


def test_a_new_producer_with_its_automatic_account_can_be_deleted(actor):
    producer = ProducerFactory(email="duena@example.com", first_name="Ana", last_name="Ejemplo")
    code = producer.member_code
    assert User.objects.filter(producer=producer).count() == 1

    delete_producer(actor, producer.pk, producer.version)

    assert not Producer.objects.filter(pk=producer.pk).exists()
    assert not User.objects.filter(producer_id=producer.pk).exists()
    event = ProducerAuditEvent.objects.get(member_code=code)
    assert event.producer_name == "Ana Ejemplo"
    assert event.actor == actor
    assert (event.farms_deleted, event.accounts_deleted) == (0, 1)


def test_farms_without_records_go_with_the_producer_and_leave_their_audit(actor):
    producer = ProducerFactory()
    farms = FarmFactory.create_batch(2, producer=producer)

    delete_producer(actor, producer.pk, producer.version)

    assert not Farm.objects.filter(pk__in=[farm.pk for farm in farms]).exists()
    deleted = FarmAuditEvent.objects.filter(
        farm_ref__in=[farm.pk for farm in farms], action=FarmAuditEvent.Action.DELETED
    )
    assert deleted.count() == 2
    assert all(event.farm is None for event in deleted)
    assert ProducerAuditEvent.objects.get().farms_deleted == 2


def test_one_important_dependent_blocks_everything_even_what_could_be_deleted(
    actor, farm_dependent_model
):
    producer = ProducerFactory()
    free = FarmFactory(producer=producer, name="Sin registros")
    busy = FarmFactory(producer=producer, name="Con registros")
    farm_dependent_model.objects.create(farm=busy)
    employee = UserFactory(producer=producer)

    with pytest.raises(ProducerHasRecords):
        delete_producer(actor, producer.pk, producer.version)

    assert Producer.objects.filter(pk=producer.pk).exists()
    assert Farm.objects.filter(pk__in=[free.pk, busy.pk]).count() == 2
    assert User.objects.filter(pk=employee.pk).exists()
    assert not ProducerAuditEvent.objects.exists()
    assert not FarmAuditEvent.objects.filter(action=FarmAuditEvent.Action.DELETED).exists()


def test_the_owner_who_already_signed_in_blocks_the_deletion(actor):
    producer = ProducerFactory(email="duena@example.com")
    (owner,) = User.objects.filter(producer=producer)
    _sign_in(owner)

    with pytest.raises(ProducerHasRecords) as error:
        delete_producer(actor, producer.pk, producer.version)

    assert "ya inició sesión" in str(error.value.detail)
    assert Producer.objects.filter(pk=producer.pk).exists()
    assert User.objects.filter(pk=owner.pk).exists()


@pytest.mark.parametrize("enabled", [True, False])
def test_the_association_access_switch_does_not_change_the_result(actor, enabled):
    producer = ProducerFactory()
    UserFactory(producer=producer)
    if enabled:
        enable_association_access(producer)

    delete_producer(actor, producer.pk, producer.version)

    assert not Producer.objects.filter(pk=producer.pk).exists()
    assert not AssociationAccess.objects.filter(producer_id=producer.pk).exists()


def test_a_stale_version_deletes_nothing(actor):
    producer = ProducerFactory()
    FarmFactory(producer=producer)

    with pytest.raises(StaleVersion):
        delete_producer(actor, producer.pk, producer.version + 1)

    assert Producer.objects.filter(pk=producer.pk).exists()
    assert Farm.objects.filter(producer=producer).exists()


def test_a_producer_that_does_not_exist_is_not_found(actor):
    import uuid

    with pytest.raises(ProducerNotFound):
        delete_producer(actor, uuid.uuid4(), 1)


def test_the_deleted_member_code_is_not_reused(actor):
    # Con el alta real, que es la que usa la secuencia de códigos.
    data = {
        "document_type": "CC",
        "identity_document": "12345678",
        "first_name": "Ana",
        "last_name": "Gomez",
        "municipality_code": "54001",
        "joined_on": "2026-09-21",
    }
    created = create_producer(data)

    delete_producer(actor, created.pk, created.version)
    next_one = create_producer({**data, "identity_document": "87654321"})

    assert next_one.member_code > created.member_code


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_deletions_leave_one_winner_and_a_clean_not_found(actor):
    producer = ProducerFactory()
    barrier = Barrier(2)

    def attempt(_):
        try:
            barrier.wait()
            delete_producer(actor, producer.pk, producer.version)
            return "deleted"
        except ProducerNotFound:
            return "not_found"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(attempt, range(2)))

    assert outcomes == ["deleted", "not_found"]
    assert ProducerAuditEvent.objects.count() == 1
