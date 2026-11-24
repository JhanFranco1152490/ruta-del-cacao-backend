"""La fermentación en la bitácora: el lote, el cajón y el responsable por su nombre, y los
volteos dentro de su lote."""

from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.contracts.audit_log import audit_source
from apps.common.serializers import full_name
from apps.fermentation.services import turns
from apps.fermentation.services.audit import record_process_event, start_values
from apps.fermentation.tests.factories import FermentationProcessFactory, FermentationTurnFactory

pytestmark = pytest.mark.django_db


def test_a_start_shows_the_box_and_the_person_in_charge_by_name():
    process = FermentationProcessFactory(facility__name="C-01")
    event = record_process_event(
        process=process, actor=None, action="started", before={}, after=start_values(process)
    )

    [entry] = audit_source("fermentation").describe([event.pk])

    assert entry.record_label == f"Lote {process.lot.code}"
    assert entry.record_id == process.lot_id
    changes = {change.field: change for change in entry.changes}
    assert changes["facility_id"].after == "C-01"
    assert changes["responsible_id"].after == full_name(process.responsible)
    assert changes["started_at"].kind == "datetime"
    assert changes["over_capacity"].kind == "bool"


def test_a_turn_is_named_inside_its_lot_with_its_measures():
    turn = FermentationTurnFactory(temperature_c=Decimal("45.0"), ph=Decimal("4.90"))
    turns._record(turn, UserFactory(), "turn_created", {}, {"temperature_c": "45.0", "ph": "4.90"})
    event = turn.process.audit_events.get(action="turn_created")

    [entry] = audit_source("fermentation").describe([event.pk])

    assert entry.record_label == f"Lote {turn.process.lot.code} · volteo"
    assert entry.action_label == "Volteo registrado"
    changes = {change.field: change for change in entry.changes}
    assert (changes["temperature_c"].label, changes["temperature_c"].kind) == (
        "Temperatura (°C)",
        "number",
    )


def test_many_events_take_the_same_queries(django_assert_max_num_queries):
    process = FermentationProcessFactory()
    events = [
        record_process_event(
            process=process, actor=UserFactory(), action="updated", before={}, after={}
        )
        for _ in range(30)
    ]

    # Los eventos con su lote, los cajones y los responsables.
    with django_assert_max_num_queries(3):
        entries = audit_source("fermentation").describe([event.pk for event in events])

    assert len(entries) == 30
