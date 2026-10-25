from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from .factories import DryingLogEntryFactory, DryingProcessFactory

pytestmark = pytest.mark.django_db

RESULT = {
    "final_moisture_pct": Decimal("7.0"),
    "dry_weight_kg": Decimal("313.2"),
    "yield_pct": Decimal("38.2"),
    "total_sun_hours": Decimal("31.5"),
}


def refused(build):
    """Que la base rechace lo que crea `build`, sin romper la transacción de la prueba."""
    with pytest.raises(IntegrityError), transaction.atomic():
        build()


def finished(process, **overrides):
    return {"ended_at": process.started_at + timedelta(hours=116), **RESULT, **overrides}


# --- El secado ---


def test_a_new_drying_is_in_progress_and_within_the_expected_range():
    process = DryingProcessFactory()

    assert (process.ended_at, process.yield_pct, process.entry_moisture_out_of_range) == (
        None,
        None,
        False,
    )
    assert process.version == 1


@pytest.mark.parametrize("moisture", ["0.0", "58.5", "100.0"])
def test_the_entry_moisture_is_a_percentage(moisture):
    assert DryingProcessFactory(entry_moisture_pct=Decimal(moisture)).pk


@pytest.mark.parametrize("moisture", ["-0.1", "100.1"])
def test_an_entry_moisture_out_of_range_is_refused(moisture):
    refused(lambda: DryingProcessFactory(entry_moisture_pct=Decimal(moisture)))


def test_a_finished_drying_keeps_its_whole_result():
    process = DryingProcessFactory()
    started_at = process.started_at

    assert DryingProcessFactory(started_at=started_at, **finished(process)).yield_pct == Decimal(
        "38.2"
    )


@pytest.mark.parametrize("missing", ["ended_at", *RESULT])
def test_the_result_is_all_or_nothing(missing):
    process = DryingProcessFactory()

    refused(lambda: DryingProcessFactory(**{**finished(process), missing: None}))


def test_the_end_must_come_after_the_start():
    process = DryingProcessFactory()

    refused(lambda: DryingProcessFactory(**finished(process, ended_at=process.started_at)))


@pytest.mark.parametrize(
    "overrides",
    [
        {"dry_weight_kg": Decimal("0.0")},
        {"yield_pct": Decimal("100.1")},
        {"final_moisture_pct": Decimal("100.1")},
    ],
)
def test_the_result_values_stay_in_their_range(overrides):
    process = DryingProcessFactory()

    refused(lambda: DryingProcessFactory(**finished(process, **overrides)))


def test_a_lot_has_at_most_one_drying():
    process = DryingProcessFactory()

    refused(lambda: DryingProcessFactory(lot=process.lot))


def test_an_account_that_answered_for_a_drying_is_not_deleted():
    process = DryingProcessFactory()

    with pytest.raises(ProtectedError):
        process.responsible.delete()


# --- La bitácora ---


def test_a_log_keeps_its_day_and_date():
    entry = DryingLogEntryFactory(day=3)

    assert entry.day_number == 3
    assert entry.log_date == timezone.localdate(entry.measured_at)


def test_a_day_without_sun_is_a_valid_log():
    assert DryingLogEntryFactory(sun_hours=Decimal("0.0"), weather="rainy").pk


@pytest.mark.parametrize(
    "overrides",
    [
        {"moisture_pct": Decimal("100.1")},
        {"moisture_pct": Decimal("-0.1")},
        {"sun_hours": Decimal("24.1")},
        {"shade_hours": Decimal("24.1")},
        {"turn_count": 49},
        {"day_number": 0},
        {"weather": "foggy"},
    ],
)
def test_a_log_value_out_of_range_is_refused(overrides):
    process = DryingProcessFactory()

    refused(lambda: DryingLogEntryFactory(process=process, **overrides))


@pytest.mark.parametrize(
    ("turn_count", "frequency"),
    [(0, Decimal("2.0")), (2, None), (2, Decimal("0.4")), (2, Decimal("24.1"))],
)
def test_the_turn_frequency_goes_only_with_turns_and_within_range(turn_count, frequency):
    process = DryingProcessFactory()

    refused(
        lambda: DryingLogEntryFactory(
            process=process, turn_count=turn_count, turn_frequency_hours=frequency
        )
    )


@pytest.mark.parametrize(
    ("turn_count", "frequency"), [(0, None), (1, Decimal("0.5")), (48, Decimal("24.0"))]
)
def test_the_turn_frequency_accepts_its_edges(turn_count, frequency):
    assert DryingLogEntryFactory(turn_count=turn_count, turn_frequency_hours=frequency).pk


def test_a_drying_has_one_log_per_date():
    entry = DryingLogEntryFactory()

    refused(lambda: DryingLogEntryFactory(process=entry.process, log_date=entry.log_date))
    assert DryingLogEntryFactory(process=entry.process, day=2).pk


def test_an_account_that_recorded_a_log_is_not_deleted():
    entry = DryingLogEntryFactory()

    with pytest.raises(ProtectedError):
        entry.recorded_by.delete()
