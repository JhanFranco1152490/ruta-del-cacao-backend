"""Los valores en el historial de la finca: el alta los trae todos, la edición el anterior y el
nuevo de lo que cambió y la eliminación los que tenía."""

import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.farms.models import FarmAuditEvent
from apps.farms.services.audit import VALUE_FIELDS, record_farm_audit_event
from apps.farms.services.farms import update_farm
from apps.farms.tests.factories import FarmFactory

pytestmark = pytest.mark.django_db


def _last(farm, action):
    return FarmAuditEvent.objects.filter(farm_ref=farm.pk, action=action).latest("occurred_at")


def test_an_edit_keeps_the_previous_and_the_new_value():
    farm = FarmFactory(name="La Esperanza", details="")
    owner = make_producer_owner(farm.producer)

    update_farm(owner, farm.pk, farm.version, {"name": "La Esperanza Alta", "details": "Vereda"})

    event = _last(farm, "updated")
    assert event.changes == {
        "details": {"before": "", "after": "Vereda"},
        "name": {"before": "La Esperanza", "after": "La Esperanza Alta"},
    }
    assert event.changed_fields == ["details", "name"]


def test_a_status_change_keeps_both_values():
    farm = FarmFactory()
    owner = make_producer_owner(farm.producer)

    update_farm(owner, farm.pk, farm.version, {"is_active": False})

    assert _last(farm, "status_changed").changes == {"is_active": {"before": True, "after": False}}


def test_a_creation_keeps_every_value_it_was_created_with():
    farm = FarmFactory(name="El Mirador")

    record_farm_audit_event(farm=farm, actor=None, action="created")

    changes = _last(farm, "created").changes
    assert set(changes) == set(VALUE_FIELDS)
    assert changes["name"] == {"before": None, "after": "El Mirador"}
    assert changes["area_hectares"]["after"] == str(farm.area_hectares)


def test_a_deletion_keeps_the_values_it_had():
    farm = FarmFactory(name="El Mirador")

    record_farm_audit_event(farm=farm, actor=None, action="deleted")

    assert _last(farm, "deleted").changes["name"] == {"before": "El Mirador", "after": None}
