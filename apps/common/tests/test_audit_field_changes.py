import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from apps.common.audit import field_changes


def test_only_the_fields_that_changed_are_listed_with_their_old_and_new_value():
    before = {"activity_type": "pruning", "scheduled_date": date(2026, 10, 20)}
    after = {"activity_type": "pruning", "scheduled_date": date(2026, 10, 23)}

    assert field_changes(before, after) == {
        "scheduled_date": {"before": "2026-10-20", "after": "2026-10-23"}
    }


def test_nothing_changed_gives_an_empty_dict():
    values = {"activity_type": "pruning", "quantity": Decimal("2.000")}

    assert field_changes(values, dict(values)) == {}


def test_values_are_written_as_the_api_shows_them():
    old_id, new_id = uuid.uuid4(), uuid.uuid4()
    moment = datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc)

    changes = field_changes(
        {"assignee_id": old_id, "quantity": Decimal("2.500"), "completed_at": None},
        {"assignee_id": new_id, "quantity": Decimal("3"), "completed_at": moment},
    )

    assert changes == {
        "assignee_id": {"before": str(old_id), "after": str(new_id)},
        "quantity": {"before": "2.500", "after": "3"},
        "completed_at": {"before": None, "after": "2026-10-08T14:00:00+00:00"},
    }


def test_a_field_missing_on_one_side_counts_as_empty():
    # Un registro nuevo no tiene valores anteriores: todo lo que trae aparece como cambio desde
    # vacío, y un campo que deja de existir, como cambio hacia vacío.
    assert field_changes({}, {"activity_type": "pruning"}) == {
        "activity_type": {"before": None, "after": "pruning"}
    }
    assert field_changes({"other_description": "Resiembra"}, {}) == {
        "other_description": {"before": "Resiembra", "after": None}
    }


def test_decimals_that_are_equal_in_value_are_not_a_change():
    assert field_changes({"quantity": Decimal("2.0")}, {"quantity": Decimal("2.000")}) == {}


def test_with_the_fields_given_every_one_is_listed_even_if_it_did_not_change():
    # Quien llama ya sabe qué cambió (o, en un alta, quiere todos los campos), y un campo que
    # sigue vacío también queda.
    changes = field_changes(
        {}, {"name": "Urea", "package_type": None}, fields=["package_type", "name"]
    )

    assert changes == {
        "name": {"before": None, "after": "Urea"},
        "package_type": {"before": None, "after": None},
    }


def test_with_the_fields_given_the_others_are_left_out():
    changes = field_changes(
        {"name": "Urea", "unit": "kg"}, {"name": "Urea 46 %", "unit": "g"}, fields=["name"]
    )

    assert changes == {"name": {"before": "Urea", "after": "Urea 46 %"}}


def test_decimals_can_be_written_with_fixed_places():
    changes = field_changes(
        {"package_size": None}, {"package_size": Decimal("50")}, decimal_places=3
    )

    assert changes == {"package_size": {"before": None, "after": "50.000"}}
