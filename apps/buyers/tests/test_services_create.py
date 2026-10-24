import pytest
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.buyers.exceptions import DuplicateBuyerDocument, ProducerInactive
from apps.buyers.models import Buyer, BuyerAuditEvent
from apps.buyers.services import create_buyer
from apps.common.exceptions import ProducerRequired
from apps.common.tests.concurrency import run_in_parallel
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = pytest.mark.django_db


def data(**overrides) -> dict:
    """Los datos que el serializador deja listos para el servicio."""
    fields = {
        "name": "Chocolates del Oriente S.A.S.",
        "document_type": "NIT",
        "identity_document": "900123456",
        "buyer_type": "chocolate_industry",
        "phone": "3001234567",
    }
    fields.update(overrides)
    return fields


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def member(producer):
    return UserFactory(producer=producer)


def test_creates_an_active_buyer_of_the_producer_with_its_event(member, producer):
    buyer = create_buyer(member, data())

    assert (buyer.producer_id, buyer.is_active, buyer.version) == (producer.pk, True, 1)
    assert buyer.created_by == member
    assert buyer.has_records is False
    event = BuyerAuditEvent.objects.get()
    assert (event.action, event.buyer_ref, event.actor) == ("created", buyer.pk, member)
    assert event.buyer_type == "chocolate_industry"
    assert "identity_document" in event.changed_fields


def test_a_repeated_document_is_rejected_with_the_existing_buyer(member, producer):
    existing = BuyerFactory(producer=producer, identity_document="900123456", is_active=False)

    with pytest.raises(DuplicateBuyerDocument) as error:
        create_buyer(member, data())

    assert error.value.extra["existing"] == {
        "id": str(existing.pk),
        "name": existing.name,
        "is_active": False,
    }
    assert "identity_document" in error.value.fields
    # El mensaje no repite el documento: es un dato personal cuando el comprador es una persona.
    assert "900123456" not in str(error.value.detail)
    assert Buyer.objects.count() == 1


def test_the_same_number_with_another_type_or_in_another_producer_is_accepted(member, producer):
    BuyerFactory(producer=producer, document_type="NIT", identity_document="900123456")
    BuyerFactory(document_type="NIT", identity_document="1090123456")

    create_buyer(member, data(document_type="CC"))
    create_buyer(member, data(identity_document="1090123456"))

    assert Buyer.objects.filter(producer=producer).count() == 3


def test_the_same_name_with_another_document_is_accepted(member, producer):
    BuyerFactory(producer=producer, name="Chocolates del Oriente S.A.S.")

    create_buyer(member, data())

    assert Buyer.objects.filter(producer=producer).count() == 2


def test_invalid_data_is_rejected_before_saving(member):
    with pytest.raises(ModelValidationError) as error:
        create_buyer(member, data(phone=None, email=None))

    assert set(error.value.message_dict) == {"phone", "email"}
    assert not Buyer.objects.exists()
    assert not BuyerAuditEvent.objects.exists()


def test_an_account_without_a_producer_cannot_create():
    with pytest.raises(ProducerRequired):
        create_buyer(UserFactory(), data())


def test_a_regular_account_cannot_name_a_producer(member):
    with pytest.raises(ValidationError) as error:
        create_buyer(member, data(producer_id=ProducerFactory().pk))

    assert "producer_id" in error.value.detail


def test_the_technical_account_creates_for_the_producer_it_names(producer):
    buyer = create_buyer(UserFactory(is_superuser=True), data(producer_id=producer.pk))

    assert buyer.producer_id == producer.pk


def test_the_technical_account_cannot_create_for_an_inactive_producer(producer):
    Producer.objects.filter(pk=producer.pk).update(status=Producer.Status.INACTIVE)

    with pytest.raises(ProducerInactive):
        create_buyer(UserFactory(is_superuser=True), data(producer_id=producer.pk))


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_creations_with_the_same_document_leave_one():
    owner = UserFactory(producer=ProducerFactory())

    def attempt(_):
        try:
            return create_buyer(owner, data())
        except DuplicateBuyerDocument as error:
            return error

    results = run_in_parallel(attempt, [1, 2])

    assert sum(isinstance(result, DuplicateBuyerDocument) for result in results) == 1
    assert Buyer.objects.count() == 1
    assert BuyerAuditEvent.objects.count() == 1
