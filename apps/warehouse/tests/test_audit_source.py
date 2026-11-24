"""Las existencias y las bodegas en la bitácora."""

import pytest

from apps.common.contracts.audit_log import audit_source
from apps.lots.tests.factories import LotFactory
from apps.warehouse.models import WarehouseAuditEvent
from apps.warehouse.services.audit import record_stock_event, record_warehouse_event
from apps.warehouse.tests.factories import WarehouseFactory

pytestmark = pytest.mark.django_db


def test_an_entry_shows_the_warehouse_by_its_name():
    lot = LotFactory()
    warehouse = WarehouseFactory(farm=lot.harvest.plot.farm, name="Bodega principal")
    event = record_stock_event(
        lot=lot,
        actor=None,
        action="entered",
        before={},
        after={"warehouse_id": warehouse.pk, "g1_kg": "32.5", "entry_date": "2026-11-20"},
        version=1,
    )

    [entry] = audit_source("stock").describe([event.pk])

    assert (entry.record_label, entry.action_label) == (lot.code, "Lote ingresado a bodega")
    changes = {change.field: change for change in entry.changes}
    assert changes["warehouse_id"].after == "Bodega principal"
    assert changes["entry_date"].kind == "date"


def test_an_exit_shows_its_reason_and_grade_but_not_its_internal_id():
    lot = LotFactory()
    event = record_stock_event(
        lot=lot,
        actor=None,
        action="exited",
        before={},
        after={"exit_id": "e1", "grade": "g1", "quantity_kg": "0.5", "reason": "sample"},
        version=1,
    )

    changes = {c.field: c for c in audit_source("stock").describe([event.pk])[0].changes}

    assert "exit_id" not in changes
    assert (changes["grade"].after, changes["reason"].after) == ("G1", "Muestra")


def test_a_deleted_warehouse_keeps_its_name():
    warehouse = WarehouseFactory(name="Bodega vieja")
    event = record_warehouse_event(warehouse=warehouse, actor=None, action="deleted")
    WarehouseAuditEvent.objects.filter(pk=event.pk).update(warehouse=None)

    [entry] = audit_source("warehouse").describe([event.pk])

    assert (entry.record_label, entry.record_deleted) == ("Bodega vieja", True)
