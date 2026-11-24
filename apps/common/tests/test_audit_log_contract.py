from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.common.audit import field_changes
from apps.common.contracts import audit_log
from apps.common.contracts.audit_log import (
    AUDIT_RECORD_TYPES,
    RECORD_TYPE_LABELS,
    AuditActor,
    AuditChange,
    AuditSource,
    audit_actors,
    audit_changes,
    audit_entry,
    audit_source,
    local_day_bounds,
    register_audit_actors,
    register_audit_source,
)
from apps.common.contracts.sources import SourceRegistry

BOGOTA = ZoneInfo("America/Bogota")
LABELS = {"green_weight_kg": "Peso en verde (kg)", "collector_id": "Recolector"}


@pytest.fixture
def empty_registries(monkeypatch):
    monkeypatch.setattr(
        audit_log, "_sources", SourceRegistry("de la bitácora", AUDIT_RECORD_TYPES)
    )
    monkeypatch.setattr(audit_log, "_actors", None)


def _source():
    return AuditSource(events=lambda producer_id, **filters: None, describe=lambda ids: [])


def test_the_record_types_come_in_their_order_without_repeating():
    assert AUDIT_RECORD_TYPES == (
        "farm",
        "plot",
        "plot_characterization",
        "input",
        "activity",
        "harvest",
        "lot",
        "facility",
        "fermentation",
        "drying",
        "quality",
        "stock",
        "warehouse",
        "buyer",
        "sale",
        "account",
        "role",
    )
    assert set(RECORD_TYPE_LABELS) == set(AUDIT_RECORD_TYPES)
    assert RECORD_TYPE_LABELS["plot_characterization"] == "Ficha de la parcela"


def test_a_registered_source_is_returned_by_its_type(empty_registries):
    source = _source()

    register_audit_source("harvest", source)

    assert audit_source("harvest") is source


def test_a_source_of_an_unknown_type_cannot_be_registered(empty_registries):
    with pytest.raises(ValueError):
        register_audit_source("pest", _source())


def test_asking_for_a_source_nobody_registered_fails_loudly(empty_registries):
    with pytest.raises(RuntimeError):
        audit_source("sale")


def test_the_actors_come_from_the_app_that_registered_them(empty_registries):
    actor = AuditActor(id="a", full_name="Luis Peña", is_active=True)
    register_audit_actors(lambda producer_id: [actor])

    assert audit_actors("p") == [actor]


def test_asking_for_the_actors_before_anyone_registered_them_fails_loudly(empty_registries):
    with pytest.raises(RuntimeError):
        audit_actors("p")


def test_a_change_brings_its_label_and_both_values():
    stored = {"green_weight_kg": {"before": "120.5", "after": "125.0"}}

    assert audit_changes(stored, labels=LABELS, kinds={"green_weight_kg": "number"}) == (
        AuditChange(
            field="green_weight_kg",
            label="Peso en verde (kg)",
            kind="number",
            before="120.5",
            after="125.0",
            hidden=None,
        ),
    )


def test_a_field_without_a_label_uses_its_name_and_is_text():
    [change] = audit_changes({"notes": {"before": "", "after": "Ok"}}, labels=LABELS)

    assert (change.label, change.kind) == ("notes", "text")


def test_ids_are_translated_to_names_and_an_unknown_one_stays_as_it_was():
    stored = {"collector_id": {"before": "u1", "after": "u2"}}

    [change] = audit_changes(stored, labels=LABELS, names={"collector_id": {"u1": "Luis Peña"}})

    assert (change.before, change.after, change.kind) == ("Luis Peña", "u2", "text")


def test_a_personal_field_says_it_changed_without_its_values():
    stored = {"phone": {"before": "3001234567", "after": "3007654321"}}

    [change] = audit_changes(stored, labels={"phone": "Teléfono"}, personal=("phone",))

    assert (change.label, change.before, change.after, change.hidden) == (
        "Teléfono",
        None,
        None,
        "personal",
    )


def test_a_personal_field_kept_only_by_name_is_still_personal():
    [change] = audit_changes({}, changed_fields=["phone"], labels={}, personal=("phone",))

    assert change.hidden == "personal"


def test_a_field_saved_without_its_values_is_not_recorded():
    [change] = audit_changes({}, changed_fields=["green_weight_kg"], labels=LABELS)

    assert (change.before, change.after, change.hidden) == (None, None, "not_recorded")


def test_a_creation_and_a_deletion_keep_the_empty_side():
    created = audit_changes({"green_weight_kg": {"before": None, "after": "120.5"}}, labels=LABELS)
    deleted = audit_changes({"green_weight_kg": {"before": "120.5", "after": None}}, labels=LABELS)

    assert (created[0].before, created[0].after) == (None, "120.5")
    assert (deleted[0].before, deleted[0].after) == ("120.5", None)


def test_the_changes_follow_the_order_of_the_labels_and_then_the_name():
    stored = {
        "zone": {"before": 1, "after": 2},
        "collector_id": {"before": "a", "after": "b"},
        "green_weight_kg": {"before": "1.0", "after": "2.0"},
        "alpha": {"before": 1, "after": 2},
    }

    fields = [change.field for change in audit_changes(stored, labels=LABELS)]

    assert fields == ["green_weight_kg", "collector_id", "alpha", "zone"]


def test_no_changes_give_an_empty_tuple():
    assert audit_changes({}, labels=LABELS) == ()


def test_the_local_day_bounds_cover_the_whole_days_in_bogota():
    start, end = local_day_bounds(date(2026, 11, 14), date(2026, 11, 15))

    assert start == datetime(2026, 11, 14, 0, 0, tzinfo=BOGOTA)
    assert end == datetime(2026, 11, 16, 0, 0, tzinfo=BOGOTA)
    # Las 23:30 del 15 en Bogotá ya son el 16 en UTC, y cuentan en el 15.
    assert start <= datetime(2026, 11, 15, 23, 30, tzinfo=BOGOTA) < end


def test_an_open_side_has_no_bound():
    assert local_day_bounds(None, None) == (None, None)
    assert local_day_bounds(date(2026, 11, 14), None)[1] is None


def test_field_changes_can_leave_fields_out():
    changes = field_changes(
        {"phone": "1", "buyer_type": "company"},
        {"phone": "2", "buyer_type": "person"},
        exclude=("phone",),
    )

    assert changes == {"buyer_type": {"before": "company", "after": "person"}}


def test_a_field_not_shown_says_it_changed_without_its_values():
    [change] = audit_changes(
        {}, changed_fields=["boundary"], labels={"boundary": "Polígono"}, not_shown=("boundary",)
    )

    assert (change.label, change.before, change.after, change.hidden) == (
        "Polígono",
        None,
        None,
        "not_shown",
    )


def test_a_skipped_field_does_not_come_out():
    stored = {"invoice_name": {"before": "a.pdf", "after": "b.pdf"}}

    changes = audit_changes(stored, changed_fields=["invoice"], labels={}, skip=("invoice",))

    assert [change.field for change in changes] == ["invoice_name"]


class _Event:
    pk = "e1"
    occurred_at = datetime(2026, 11, 20, 10, 0, tzinfo=BOGOTA)
    action = "updated"
    actor_id = None
    actor = None

    def get_action_display(self):
        return "Cosecha corregida"


def test_an_entry_takes_the_time_the_action_and_a_deleted_account():
    entry = audit_entry(
        _Event(),
        "harvest",
        record_id="h1",
        record_label="Cosecha del 14/11/2026 · P01",
        record_deleted=False,
        changes=(),
    )

    assert (entry.id, entry.action, entry.action_label) == ("e1", "updated", "Cosecha corregida")
    assert (entry.actor_id, entry.actor_name) == (None, None)
    assert entry.record_label == "Cosecha del 14/11/2026 · P01"
