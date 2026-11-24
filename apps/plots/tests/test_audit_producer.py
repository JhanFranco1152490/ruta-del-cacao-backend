"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.plots.models import PlotAuditEvent
from apps.plots.services.audit import record_plot_audit_event
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.plots.migrations.0008_fill_audit_producer_ref"


def _event():
    plot = PlotFactory()
    event = record_plot_audit_event(plot=plot, actor=UserFactory(), action="updated")
    return event, plot.farm.producer_id


def _orphan():
    plot = PlotFactory()
    event = record_plot_audit_event(plot=plot, actor=UserFactory(), action="deleted")
    PlotAuditEvent.objects.filter(pk=event.pk).update(plot=None)
    plot.delete()
    return event


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    PlotAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(
    _orphan is None, reason="La ficha se elimina con su parcela: no queda huérfana."
)
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan() if _orphan else None
    PlotAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
