import pytest
from django.db import IntegrityError

from apps.producers.exceptions import DuplicateDocument, ProducerNotFound, StaleVersion
from apps.producers.models import Producer
from apps.producers.services import (
    change_producer_status,
    create_producer,
    next_member_code,
    update_producer,
)
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_update_changes_only_the_given_fields_and_increments_version():
    producer = ProducerFactory()

    updated = update_producer(producer.id, 1, {"first_name": "Bea"})

    assert updated.first_name == "Bea"
    assert updated.version == 2
    assert updated.member_code == producer.member_code


def test_update_without_real_changes_keeps_the_version():
    producer = ProducerFactory(first_name="Ana")

    assert update_producer(producer.id, 1, {"first_name": "Ana"}).version == 1


def test_update_with_stale_version_raises():
    producer = ProducerFactory()

    with pytest.raises(StaleVersion):
        update_producer(producer.id, 2, {"first_name": "Bea"})


def test_update_of_unknown_producer_raises():
    with pytest.raises(ProducerNotFound):
        update_producer("00000000-0000-0000-0000-000000000000", 1, {"first_name": "Bea"})


def test_status_changes_once_per_real_change():
    producer = ProducerFactory()

    inactive = change_producer_status(producer.id, 1, Producer.Status.INACTIVE)
    repeated = change_producer_status(producer.id, 2, Producer.Status.INACTIVE)

    assert inactive.version == repeated.version == 2


def test_member_codes_are_zero_padded_and_consecutive():
    first, second = next_member_code(), next_member_code()

    assert first.startswith("PROD-") and len(first) == 11
    assert int(second.removeprefix("PROD-")) == int(first.removeprefix("PROD-")) + 1


def create_data(**overrides):
    return {
        "document_type": "CC",
        "identity_document": "12345678",
        "first_name": "Ana",
        "last_name": "Gomez",
        "municipality_code": "54001",
        "joined_on": "2026-09-21",
        **overrides,
    }


def test_create_raises_duplicate_document_for_the_unique_document_constraint():
    existing = ProducerFactory(identity_document="12345678")

    with pytest.raises(DuplicateDocument) as error:
        create_producer(create_data())

    assert error.value.extra == {"existing_producer_id": str(existing.id)}


def test_create_lets_other_integrity_errors_through(monkeypatch):
    def fail_on_another_constraint(self, *args, **kwargs):
        raise IntegrityError("otra restriccion")

    monkeypatch.setattr(Producer, "save", fail_on_another_constraint)

    with pytest.raises(IntegrityError):
        create_producer(create_data())


def test_create_does_not_report_a_member_code_collision_as_a_duplicate_document(monkeypatch):
    taken = ProducerFactory(member_code="PROD-000123")
    monkeypatch.setattr("apps.producers.services.next_member_code", lambda: taken.member_code)

    with pytest.raises(IntegrityError):
        create_producer(create_data(identity_document="87654321"))


def test_update_lets_other_integrity_errors_through(monkeypatch):
    producer = ProducerFactory()

    def fail_on_another_constraint(self, *args, **kwargs):
        raise IntegrityError("otra restriccion")

    monkeypatch.setattr(Producer, "save", fail_on_another_constraint)

    with pytest.raises(IntegrityError):
        update_producer(producer.id, 1, {"first_name": "Bea"})
