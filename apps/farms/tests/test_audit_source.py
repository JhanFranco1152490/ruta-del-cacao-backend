"""Las fincas en la bitácora: sus eventos, su etiqueta y sus cambios traducidos."""

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.common.contracts.audit_log import audit_source
from apps.farms.models import FarmAuditEvent
from apps.farms.services.audit import record_farm_audit_event
from apps.farms.services.farms import update_farm
from apps.farms.tests.factories import FarmFactory

pytestmark = pytest.mark.django_db


def _describe(*events):
    return audit_source("farm").describe([event.pk for event in events])


def test_the_events_are_only_those_of_the_producer():
    mine = record_farm_audit_event(farm=FarmFactory(), actor=None, action="updated")
    record_farm_audit_event(farm=FarmFactory(), actor=None, action="updated")

    rows = audit_source("farm").events(mine.producer_ref)

    assert [row["id"] for row in rows] == [mine.pk]


def test_an_edit_shows_its_label_its_action_and_both_values():
    farm = FarmFactory(name="La Esperanza")
    owner = make_producer_owner(farm.producer)
    update_farm(owner, farm.pk, farm.version, {"name": "La Esperanza Alta"})
    event = FarmAuditEvent.objects.get(farm_ref=farm.pk, action="updated")

    [entry] = _describe(event)

    assert (entry.record_type, entry.record_label, entry.record_deleted) == (
        "farm",
        f"{farm.code} · La Esperanza Alta",
        False,
    )
    assert (entry.action, entry.action_label, entry.actor_id) == (
        "updated",
        "Finca actualizada",
        owner.pk,
    )
    [change] = entry.changes
    assert (change.label, change.before, change.after) == (
        "Nombre",
        "La Esperanza",
        "La Esperanza Alta",
    )


def test_the_municipality_is_shown_by_its_name_and_the_area_as_a_number():
    farm = FarmFactory(municipality_code="54810")
    event = record_farm_audit_event(farm=farm, actor=None, action="created")

    changes = {change.field: change for change in _describe(event)[0].changes}

    assert changes["municipality_code"].after == "Tibú"
    assert changes["area_hectares"].kind == "number"
    assert changes["is_active"].kind == "bool"


def test_a_deleted_farm_keeps_its_name():
    farm = FarmFactory(name="El Mirador")
    event = record_farm_audit_event(farm=farm, actor=UserFactory(), action="deleted")
    FarmAuditEvent.objects.filter(pk=event.pk).update(farm=None)

    [entry] = _describe(event)

    assert (entry.record_label, entry.record_deleted) == ("El Mirador", True)


def test_an_event_saved_without_values_says_they_were_not_recorded():
    farm = FarmFactory()
    event = FarmAuditEvent.record(
        farm=farm,
        farm_ref=farm.pk,
        farm_name=farm.name,
        producer_ref=farm.producer_id,
        actor=None,
        action="updated",
        changed_fields=["name"],
    )

    [change] = _describe(event)[0].changes

    assert (change.label, change.hidden) == ("Nombre", "not_recorded")


def test_many_events_take_the_same_queries(django_assert_num_queries):
    farm = FarmFactory()
    events = [
        record_farm_audit_event(farm=farm, actor=UserFactory(), action="updated")
        for _ in range(30)
    ]

    with django_assert_num_queries(1):
        entries = _describe(*events)

    assert len(entries) == 30
