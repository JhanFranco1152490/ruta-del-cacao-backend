"""El productor de cada evento de cuentas y roles: se toma de la cuenta o del rol sobre el que se
actúa, y la migración de datos lo completa en lo que ya existía."""

import importlib
import uuid

import pytest
from django.apps import apps

from apps.accounts.events import record_account_event
from apps.accounts.models import AccountManagementEvent
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.accounts.migrations.0018_fill_event_producer_ref"
EventType = AccountManagementEvent.EventType


def _last():
    return AccountManagementEvent.objects.latest("occurred_at")


def test_an_account_event_takes_the_producer_of_the_account():
    employee = UserFactory(producer=ProducerFactory())

    record_account_event(EventType.ACCOUNT_DEACTIVATED, uuid.uuid4(), target_user=employee)

    assert _last().producer_ref == employee.producer_id


def test_a_role_event_takes_the_producer_of_the_role():
    role = RoleFactory(producer=ProducerFactory())

    record_account_event(EventType.ROLE_UPDATED, uuid.uuid4(), target_role_id=role.pk)

    assert _last().producer_ref == role.producer_id


def test_a_deleted_role_or_account_passes_its_producer_explicitly():
    producer = ProducerFactory()

    record_account_event(
        EventType.ROLE_DELETED, uuid.uuid4(), target_role_id=uuid.uuid4(), producer_ref=producer.pk
    )

    assert _last().producer_ref == producer.pk


def test_an_account_of_the_association_has_no_producer():
    record_account_event(EventType.ACCOUNT_CREATED, uuid.uuid4(), target_user=UserFactory())

    assert _last().producer_ref is None


def test_the_data_migration_fills_the_events_of_accounts_and_roles():
    employee = UserFactory(producer=ProducerFactory())
    role = RoleFactory(producer=ProducerFactory())
    record_account_event(EventType.ACCOUNT_ROLES_CHANGED, uuid.uuid4(), target_user=employee)
    record_account_event(EventType.ROLE_CREATED, uuid.uuid4(), target_role_id=role.pk)
    AccountManagementEvent.objects.update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    producers = set(AccountManagementEvent.objects.values_list("producer_ref", flat=True))
    assert producers == {employee.producer_id, role.producer_id}


def test_an_event_of_a_deleted_account_stays_empty():
    record_account_event(EventType.ACCOUNT_DELETED, uuid.uuid4(), target_user_ref=uuid.uuid4())
    AccountManagementEvent.objects.update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    assert _last().producer_ref is None
