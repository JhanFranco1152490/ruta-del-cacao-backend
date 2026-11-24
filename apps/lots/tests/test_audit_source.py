"""Los lotes en la bitácora: su código y su estado por su etiqueta."""

import pytest

from apps.common.contracts.audit_log import audit_source
from apps.lots.models import LotAuditEvent
from apps.lots.services.audit import record_lot_event
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db


def test_a_status_change_shows_the_code_and_both_statuses():
    lot = LotFactory()
    event = record_lot_event(
        lot=lot,
        actor=None,
        action="status_changed",
        before={"status": "generated"},
        after={"status": "fermenting"},
    )

    [entry] = audit_source("lot").describe([event.pk])

    assert (entry.record_label, entry.action_label) == (lot.code, "Estado del lote modificado")
    [change] = entry.changes
    assert (change.label, change.before, change.after) == ("Estado", "Generado", "En fermentación")


def test_a_deleted_lot_keeps_its_code():
    lot = LotFactory()
    event = record_lot_event(lot=lot, actor=None, action="deleted")
    LotAuditEvent.objects.filter(pk=event.pk).update(lot=None)

    [entry] = audit_source("lot").describe([event.pk])

    assert (entry.record_label, entry.record_deleted) == (lot.code, True)


def test_the_events_are_only_those_of_the_producer():
    mine = record_lot_event(lot=LotFactory(), actor=None, action="created")
    record_lot_event(lot=LotFactory(), actor=None, action="created")

    assert [row["id"] for row in audit_source("lot").events(mine.producer_ref)] == [mine.pk]
