"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.harvests.models import HarvestAuditEvent
from apps.harvests.services.audit import harvest_values, record_harvest_event
from apps.harvests.tests.factories import HarvestFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.harvests.migrations.0003_fill_audit_producer_ref"


def _event():
    harvest = HarvestFactory()
    values = harvest_values(harvest)
    event = record_harvest_event(
        harvest=harvest, actor=UserFactory(), action="updated", before=values, after=values
    )
    return event, harvest.plot.farm.producer_id


def _orphan():
    harvest = HarvestFactory()
    values = harvest_values(harvest)
    event = record_harvest_event(
        harvest=harvest, actor=UserFactory(), action="updated", before=values, after=values
    )
    # La parcela de la cosecha ya no existe: el evento no tiene cómo llegar a su productor.
    HarvestAuditEvent.objects.filter(pk=event.pk).update(
        harvest=None, plot_ref="00000000-0000-0000-0000-000000000000"
    )
    return event


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    HarvestAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(
    _orphan is None, reason="La ficha se elimina con su parcela: no queda huérfana."
)
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan() if _orphan else None
    HarvestAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
