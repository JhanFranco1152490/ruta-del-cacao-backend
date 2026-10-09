from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.common.exceptions import ProducerRequired
from apps.common.tests.concurrency import run_in_parallel
from apps.inputs.exceptions import DuplicateInput, ProducerInactive
from apps.inputs.models import AgriculturalInput, AgriculturalInputAuditEvent
from apps.inputs.services import create_input
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory, input_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def member(producer):
    return UserFactory(producer=producer)


def test_creates_an_active_input_in_the_catalog_of_the_producer(member, producer):
    item = create_input(member, input_data(name=" Urea 46 % "))

    assert item.producer_id == producer.pk
    assert (item.name, item.is_active, item.version, item.has_records) == (
        "Urea 46 %",
        True,
        1,
        False,
    )


def test_leaves_a_created_event_with_every_field_and_no_previous_value(member):
    item = create_input(member, input_data(unit="bag", bag_weight_kg=Decimal("50")))

    event = AgriculturalInputAuditEvent.objects.get()
    assert (event.action, event.actor_id, event.input_id, event.version) == (
        "created",
        member.pk,
        item.pk,
        1,
    )
    assert event.changes["name"] == {"before": None, "after": "Urea 46 %"}
    assert event.changes["bag_weight_kg"] == {"before": None, "after": "50.00"}
    assert event.changes["unit"] == {"before": None, "after": "bag"}


def test_a_name_that_only_differs_in_case_accents_spaces_or_dashes_is_a_duplicate(
    member, producer
):
    existing = create_input(member, input_data(name="Urea 46 %"))

    with pytest.raises(DuplicateInput) as error:
        create_input(member, input_data(name="UREA-46%"))

    assert error.value.extra["existing"] == {
        "id": str(existing.pk),
        "name": "Urea 46 %",
        "input_type": "fertilizer",
        "is_active": True,
    }
    assert AgriculturalInput.objects.count() == 1
    assert AgriculturalInputAuditEvent.objects.count() == 1


def test_an_inactive_input_still_counts_as_a_duplicate_and_says_so(member, producer):
    AgriculturalInputFactory(
        producer=producer, name="Urea", name_normalized="urea", is_active=False
    )

    with pytest.raises(DuplicateInput) as error:
        create_input(member, input_data(name="urea"))

    assert error.value.extra["existing"]["is_active"] is False


def test_the_same_name_with_another_type_or_another_producer_is_accepted(member):
    create_input(member, input_data(name="Cobre", input_type="fungicide"))

    create_input(member, input_data(name="Cobre", input_type="other"))
    create_input(UserFactory(producer=ProducerFactory()), input_data(name="Cobre"))

    assert AgriculturalInput.objects.count() == 3


def test_an_invalid_input_is_not_saved(member):
    with pytest.raises(Exception) as error:
        create_input(member, input_data(unit="bag"))

    assert "bag_weight_kg" in error.value.message_dict
    assert AgriculturalInput.objects.count() == 0


def test_a_failing_audit_rolls_the_input_back(member, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("apps.inputs.services.create.record_input_audit_event", fail)

    with pytest.raises(RuntimeError):
        create_input(member, input_data())

    assert AgriculturalInput.objects.count() == 0


def test_the_technical_account_names_the_producer(producer):
    technical = UserFactory(is_superuser=True)

    item = create_input(technical, input_data(producer_id=producer.pk))

    assert item.producer_id == producer.pk
    assert AgriculturalInputAuditEvent.objects.get().actor_id == technical.pk


def test_the_technical_account_must_name_an_existing_producer():
    technical = UserFactory(is_superuser=True)

    with pytest.raises(ValidationError) as missing:
        create_input(technical, input_data())
    with pytest.raises(ValidationError) as unknown:
        create_input(technical, input_data(producer_id="6f1a7e0e-0000-4000-8000-000000000000"))

    assert "producer_id" in missing.value.detail
    assert "producer_id" in unknown.value.detail


def test_the_technical_account_cannot_create_for_an_inactive_producer(producer):
    Producer.objects.filter(pk=producer.pk).update(status=Producer.Status.INACTIVE)

    with pytest.raises(ProducerInactive):
        create_input(UserFactory(is_superuser=True), input_data(producer_id=producer.pk))


def test_other_accounts_cannot_name_a_producer(member, producer):
    with pytest.raises(ValidationError) as error:
        create_input(member, input_data(producer_id=producer.pk))

    assert "producer_id" in error.value.detail


def test_an_account_without_a_producer_cannot_create():
    with pytest.raises(ProducerRequired):
        create_input(UserFactory(), input_data())


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_creations_with_the_same_name_leave_one():
    owner = UserFactory(producer=ProducerFactory())

    def attempt(_):
        try:
            return create_input(owner, input_data())
        except DuplicateInput as error:
            return error

    results = run_in_parallel(attempt, [1, 2])

    assert sum(isinstance(result, DuplicateInput) for result in results) == 1
    assert AgriculturalInput.objects.count() == 1
    assert AgriculturalInputAuditEvent.objects.count() == 1
