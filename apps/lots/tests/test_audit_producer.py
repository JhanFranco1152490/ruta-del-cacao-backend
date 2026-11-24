"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.lots.models import LotAuditEvent
from apps.lots.services.audit import record_lot_event
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.lots.migrations.0006_fill_audit_producer_ref"


def _event():
    lot = LotFactory()
    event = record_lot_event(lot=lot, actor=UserFactory(), action="status_changed")
    return event, lot.harvest.plot.farm.producer_id


def _orphan():
    lot = LotFactory()
    event = record_lot_event(lot=lot, actor=UserFactory(), action="deleted")
    # La cosecha del lote ya no existe: el evento no tiene cómo llegar a su productor.
    LotAuditEvent.objects.filter(pk=event.pk).update(
        lot=None, harvest_ref="00000000-0000-0000-0000-000000000000"
    )
    return event


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    LotAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(_orphan is None, reason="Su registro no se elimina: no queda huérfano.")
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan()
    LotAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
