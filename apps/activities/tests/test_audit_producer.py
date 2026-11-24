"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.activities.models import AgriculturalActivityAuditEvent
from apps.activities.services.audit import plan_values, record_activity_event
from apps.activities.tests.factories import AgriculturalActivityFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.activities.migrations.0005_fill_audit_producer_ref"


def _event():
    activity = AgriculturalActivityFactory()
    values = plan_values(activity)
    event = record_activity_event(
        activity=activity, actor=UserFactory(), action="updated", before=values, after=values
    )
    return event, activity.plot.farm.producer_id


def _orphan():
    activity = AgriculturalActivityFactory()
    values = plan_values(activity)
    event = record_activity_event(
        activity=activity, actor=UserFactory(), action="deleted", before=values, after={}
    )
    # La parcela de la actividad ya no existe: el evento no tiene cómo llegar a su productor.
    AgriculturalActivityAuditEvent.objects.filter(pk=event.pk).update(
        activity=None, plot_ref="00000000-0000-0000-0000-000000000000"
    )
    return event


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    AgriculturalActivityAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(
    _orphan is None, reason="La ficha se elimina con su parcela: no queda huérfana."
)
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan() if _orphan else None
    AgriculturalActivityAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
