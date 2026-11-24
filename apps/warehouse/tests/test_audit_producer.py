"""El productor de cada evento del historial: se guarda al registrarlo y la migración de datos lo
completa en lo que ya existía."""

import importlib

import pytest
from django.apps import apps

from apps.accounts.tests.factories import UserFactory
from apps.lots.tests.factories import LotFactory
from apps.warehouse.models import StockAuditEvent, WarehouseAuditEvent
from apps.warehouse.services.audit import record_stock_event, record_warehouse_event
from apps.warehouse.tests.factories import WarehouseFactory

pytestmark = pytest.mark.django_db

MIGRATION = "apps.warehouse.migrations.0005_fill_audit_producer_ref"


def _event():
    warehouse = WarehouseFactory()
    event = record_warehouse_event(warehouse=warehouse, actor=UserFactory(), action="updated")
    return event, warehouse.farm.producer_id


def _orphan():
    warehouse = WarehouseFactory()
    event = record_warehouse_event(warehouse=warehouse, actor=UserFactory(), action="deleted")
    # La finca ya no existe: el evento no tiene cómo llegar a su productor.
    WarehouseAuditEvent.objects.filter(pk=event.pk).update(
        warehouse=None, farm_ref="00000000-0000-0000-0000-000000000000"
    )
    return event


def _stock_event():
    lot = LotFactory()
    event = record_stock_event(
        lot=lot, actor=UserFactory(), action="entered", before={}, after={}, version=1
    )
    return event, lot.harvest.plot.farm.producer_id


def test_a_stock_event_keeps_the_producer_of_its_lot():
    event, producer_id = _stock_event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_stock_event():
    event, producer_id = _stock_event()
    StockAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_an_event_keeps_the_producer_of_its_record():
    event, producer_id = _event()

    event.refresh_from_db()
    assert event.producer_ref == producer_id


def test_the_data_migration_fills_the_producer_of_an_existing_event():
    event, producer_id = _event()
    WarehouseAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref == producer_id


@pytest.mark.skipif(_orphan is None, reason="Su registro no se elimina: no queda huérfano.")
def test_an_event_without_a_way_to_its_producer_stays_empty():
    event = _orphan()
    WarehouseAuditEvent.objects.filter(pk=event.pk).update(producer_ref=None)

    importlib.import_module(MIGRATION).fill_producer_ref(apps, None)

    event.refresh_from_db()
    assert event.producer_ref is None
