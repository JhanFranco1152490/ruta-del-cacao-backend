"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.buyers.models import BuyerAuditEvent
from apps.buyers.services.audit import record_buyer_audit_event
from apps.buyers.tests.factories import BuyerFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.buyers.migrations.0003_fill_audit_producer_ref"


def _event():
    buyer = BuyerFactory()
    event = record_buyer_audit_event(buyer=buyer, actor=UserFactory(), action="updated")
    return event, buyer.producer_id


def test_an_event_keeps_the_producer_of_its_buyer():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    BuyerAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_an_event_of_a_deleted_buyer_stays_empty():
    event, _ = _event()
    # El comprador ya no existe: el evento no tiene cómo llegar a su productor.
    BuyerAuditEvent.objects.filter(pk=event.pk).update(
        buyer=None, buyer_ref="00000000-0000-0000-0000-000000000000", producer_ref=None
    )

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
