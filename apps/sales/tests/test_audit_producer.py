"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.sales.models import SaleAuditEvent
from apps.sales.services.audit import record_sale_event
from apps.sales.tests.factories import SaleFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.sales.migrations.0003_fill_audit_producer_ref"


def _event():
    sale = SaleFactory()
    event = record_sale_event(
        sale=sale, actor=UserFactory(), action="voided", changed_fields=["void_reason"]
    )
    return event, sale.producer_id


def test_an_event_keeps_the_producer_of_its_sale():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id
    assert (event.action, event.changed_fields, event.version) == ("voided", ["void_reason"], 1)


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    SaleAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id
