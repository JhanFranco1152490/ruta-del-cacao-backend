"""Los insumos en la bitácora: sus opciones por su etiqueta."""

import pytest

from apps.common.contracts.audit_log import audit_source
from apps.inputs.models import AgriculturalInputAuditEvent
from apps.inputs.services.audit import record_input_audit_event
from apps.inputs.tests.factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


def test_the_type_of_an_input_is_shown_by_its_label():
    item = AgriculturalInputFactory(name="Urea", input_type="fertilizer")
    event = record_input_audit_event(
        item=item,
        actor=None,
        action="updated",
        changed_fields=["input_type"],
        before={"input_type": "other"},
    )

    [entry] = audit_source("input").describe([event.pk])

    assert entry.record_label == "Urea"
    [change] = entry.changes
    assert (change.label, change.before, change.after) == ("Tipo", "Otro", "Fertilizante")


def test_a_deleted_input_keeps_its_name():
    item = AgriculturalInputFactory(name="Urea")
    event = record_input_audit_event(item=item, actor=None, action="deleted")
    AgriculturalInputAuditEvent.objects.filter(pk=event.pk).update(input=None)

    [entry] = audit_source("input").describe([event.pk])

    assert (entry.record_label, entry.record_deleted) == ("Urea", True)
