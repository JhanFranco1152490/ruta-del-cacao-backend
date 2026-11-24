"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.inputs.models import AgriculturalInputAuditEvent
from apps.inputs.services.audit import record_input_audit_event
from apps.inputs.tests.factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.inputs.migrations.0004_fill_audit_producer_ref"


def _event():
    item = AgriculturalInputFactory()
    event = record_input_audit_event(item=item, actor=UserFactory(), action="updated")
    return event, item.producer_id


def _orphan():
    item = AgriculturalInputFactory()
    event = record_input_audit_event(item=item, actor=UserFactory(), action="deleted")
    AgriculturalInputAuditEvent.objects.filter(pk=event.pk).update(input=None)
    item.delete()
    return event


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    AgriculturalInputAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(
    _orphan is None, reason="La ficha se elimina con su parcela: no queda huérfana."
)
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan() if _orphan else None
    AgriculturalInputAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
