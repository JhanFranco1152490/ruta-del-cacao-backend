"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.crops.models import PlotCharacterizationAuditEvent
from apps.crops.services.audit import record_characterization_audit_event
from apps.crops.tests.factories import PlotCharacterizationFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.crops.migrations.0007_fill_audit_producer_ref"


def _event():
    characterization = PlotCharacterizationFactory()
    event = record_characterization_audit_event(
        characterization=characterization,
        actor=UserFactory(),
        action="updated",
        changed_fields=["shade_type"],
        plantings=[],
    )
    return event, characterization.plot.farm.producer_id


_orphan = None


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    PlotCharacterizationAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(
    _orphan is None, reason="La ficha se elimina con su parcela: no queda huérfana."
)
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan() if _orphan else None
    PlotCharacterizationAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
