"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.fermentation.models import FermentationProcessAuditEvent
from apps.fermentation.services import turns
from apps.fermentation.services.audit import record_process_event
from apps.fermentation.tests.factories import (
    FermentationProcessFactory,
    FermentationTurnFactory,
)

pytestmark = pytest.mark.django_db

MIGRATION = "apps.fermentation.migrations.0003_fill_audit_producer_ref"


def _event():
    process = FermentationProcessFactory()
    event = record_process_event(
        process=process, actor=UserFactory(), action="updated", before={}, after={}
    )
    return event, process.lot.harvest.plot.farm.producer_id


# El proceso nunca se elimina: su evento siempre llega al productor.
_orphan = None


def test_a_turn_event_keeps_the_producer_too():
    turn = FermentationTurnFactory()

    turns._record(turn, UserFactory(), "turn_created", {}, {"ph": "4.90"})

    event = FermentationProcessAuditEvent.objects.get(turn_ref=turn.pk)
    assert event.producer_ref == turn.process.lot.harvest.plot.farm.producer_id


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    FermentationProcessAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(_orphan is None, reason="Su registro no se elimina: no queda huérfano.")
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan()
    FermentationProcessAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
