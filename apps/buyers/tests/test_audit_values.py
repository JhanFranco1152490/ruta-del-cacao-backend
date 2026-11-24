"""Los valores en el historial del comprador, sin sus datos personales: de esos solo queda que
cambiaron."""

import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.buyers.models import BuyerAuditEvent
from apps.buyers.services.audit import PERSONAL_FIELDS, record_buyer_audit_event
from apps.buyers.services.update import update_buyer
from apps.buyers.tests.factories import BuyerFactory

pytestmark = pytest.mark.django_db


def _last(buyer, action):
    return BuyerAuditEvent.objects.filter(buyer_ref=buyer.pk, action=action).latest("occurred_at")


def test_an_edit_keeps_the_values_but_not_the_personal_ones():
    buyer = BuyerFactory(phone="3001234567", buyer_type="chocolate_industry")
    owner = make_producer_owner(buyer.producer)

    update_buyer(owner, buyer.pk, buyer.version, {"phone": "3007654321", "buyer_type": "exporter"})

    event = _last(buyer, "updated")
    assert sorted(event.changed_fields) == ["buyer_type", "phone"]
    assert event.changes == {"buyer_type": {"before": "chocolate_industry", "after": "exporter"}}


def test_a_creation_keeps_only_the_values_that_are_not_personal():
    buyer = BuyerFactory()

    record_buyer_audit_event(buyer=buyer, actor=None, action="created")

    changes = _last(buyer, "created").changes
    assert set(changes) == {"buyer_type", "is_active"}
    assert not set(changes) & set(PERSONAL_FIELDS)
    assert {"name", "identity_document", "phone", "email"} <= set(PERSONAL_FIELDS)
