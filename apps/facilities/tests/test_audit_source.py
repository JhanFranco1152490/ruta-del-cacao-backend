"""Los cajones y las marquesinas en la bitácora: su tipo, su nombre y el lote que los ocupa."""

import pytest

from apps.common.contracts.audit_log import audit_source
from apps.facilities.models import PostharvestFacilityAuditEvent
from apps.facilities.services.audit import record_facility_audit_event, record_occupancy_event
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db


def test_a_facility_is_named_by_its_type_and_its_name():
    facility = PostharvestFacilityFactory(facility_type="fermentation_box", name="C-01")
    event = record_facility_audit_event(
        facility=facility,
        actor=None,
        action="updated",
        changed_fields=["capacity_kg"],
        before={"capacity_kg": "300.0"},
    )

    [entry] = audit_source("facility").describe([event.pk])

    assert entry.record_label == "Cajón C-01"
    [change] = entry.changes
    assert (change.label, change.kind, change.before) == ("Capacidad (kg)", "number", "300.0")


def test_the_lot_that_occupies_it_is_shown_by_its_code():
    facility = PostharvestFacilityFactory()
    lot = LotFactory(harvest__plot__farm=facility.farm)
    event = record_occupancy_event(
        facility=facility, actor=None, action="occupied", before_lot=None, after_lot=lot
    )

    [change] = audit_source("facility").describe([event.pk])[0].changes

    assert (change.label, change.before, change.after) == ("Lote", None, lot.code)


def test_a_deleted_facility_keeps_its_name():
    facility = PostharvestFacilityFactory(name="M-02")
    event = record_facility_audit_event(facility=facility, actor=None, action="deleted")
    PostharvestFacilityAuditEvent.objects.filter(pk=event.pk).update(facility=None)

    [entry] = audit_source("facility").describe([event.pk])

    assert (entry.record_label, entry.record_deleted) == ("M-02", True)
