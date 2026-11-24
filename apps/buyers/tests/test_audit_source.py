"""Los compradores en la bitácora: sus datos personales dicen que cambiaron, sin sus valores."""

import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.buyers.models import BuyerAuditEvent
from apps.buyers.services.audit import record_buyer_audit_event
from apps.buyers.services.update import update_buyer
from apps.buyers.tests.factories import BuyerFactory
from apps.common.contracts.audit_log import audit_source

pytestmark = pytest.mark.django_db


def _describe(*events):
    return audit_source("buyer").describe([event.pk for event in events])


def test_a_phone_change_is_hidden_and_the_type_is_shown_by_its_label():
    buyer = BuyerFactory(name="Chocolates del Oriente", buyer_type="chocolate_industry")
    owner = make_producer_owner(buyer.producer)
    update_buyer(owner, buyer.pk, buyer.version, {"phone": "3007654321", "buyer_type": "exporter"})
    event = BuyerAuditEvent.objects.get(buyer_ref=buyer.pk, action="updated")

    [entry] = _describe(event)

    assert (entry.record_label, entry.action_label) == (
        "Chocolates del Oriente",
        "Comprador actualizado",
    )
    changes = {change.field: change for change in entry.changes}
    assert (changes["buyer_type"].before, changes["buyer_type"].after) == (
        "Industria chocolatera",
        "Exportador",
    )
    assert (changes["phone"].label, changes["phone"].hidden, changes["phone"].after) == (
        "Teléfono",
        "personal",
        None,
    )


def test_a_deleted_buyer_is_named_by_its_type():
    buyer = BuyerFactory(buyer_type="exporter")
    event = record_buyer_audit_event(buyer=buyer, actor=None, action="deleted")
    BuyerAuditEvent.objects.filter(pk=event.pk).update(buyer=None)

    [entry] = _describe(event)

    assert (entry.record_label, entry.record_deleted) == ("Comprador (Exportador)", True)
