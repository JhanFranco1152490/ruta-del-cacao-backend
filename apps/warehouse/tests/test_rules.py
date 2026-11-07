"""Las reglas puras de bodega."""

from datetime import date
from decimal import Decimal

import pytest

from apps.warehouse import rules
from apps.warehouse.choices import MANUAL_EXIT_REASONS, ExitReason

TODAY = date(2026, 10, 30)
CLASSIFIED_ON = date(2026, 10, 28)


@pytest.mark.parametrize(
    ("entry_date", "expected"),
    [
        (TODAY, []),
        (CLASSIFIED_ON, []),
        (date(2026, 10, 29), []),
        (date(2026, 10, 31), [rules.DATE_IN_FUTURE]),
        (date(2026, 10, 27), [rules.ENTRY_BEFORE_CLASSIFICATION]),
    ],
)
def test_the_entry_is_neither_in_the_future_nor_before_the_classification(entry_date, expected):
    assert (
        rules.entry_date_errors(entry_date, today=TODAY, classified_on=CLASSIFIED_ON) == expected
    )


def test_a_classification_in_the_future_keeps_the_future_message_first():
    errors = rules.entry_date_errors(date(2026, 11, 5), today=TODAY, classified_on=CLASSIFIED_ON)

    assert errors == [rules.DATE_IN_FUTURE]


@pytest.mark.parametrize(
    ("exit_date", "expected"),
    [
        (TODAY, []),
        (date(2026, 10, 29), []),
        (date(2026, 10, 28), []),
        (date(2026, 10, 31), [rules.DATE_IN_FUTURE]),
        (date(2026, 10, 27), [rules.EXIT_BEFORE_ENTRY]),
    ],
)
def test_an_exit_is_neither_in_the_future_nor_before_the_entry(exit_date, expected):
    assert (
        rules.exit_date_errors(exit_date, today=TODAY, entered_on=date(2026, 10, 28)) == expected
    )


@pytest.mark.parametrize(
    ("reason", "detail", "expected"),
    [
        (ExitReason.OTHER, "", [rules.DETAIL_REQUIRED]),
        (ExitReason.OTHER, "   ", [rules.DETAIL_REQUIRED]),
        (ExitReason.OTHER, "Donación a la escuela", []),
        (ExitReason.SAMPLE, "", []),
        (ExitReason.SHRINKAGE, "Se pesó de nuevo", []),
    ],
)
def test_other_needs_a_written_detail(reason, detail, expected):
    assert rules.exit_detail_errors(reason, detail) == expected


def test_what_remains_is_what_entered_minus_what_left():
    assert rules.remaining(Decimal("250.0"), Decimal("5.0")) == Decimal("245.0")
    assert rules.remaining(Decimal("250.0"), Decimal("250.0")) == Decimal("0.0")


def test_sale_is_a_reason_but_not_one_to_pick_by_hand():
    assert ExitReason.SALE in set(ExitReason)
    assert "sale" not in MANUAL_EXIT_REASONS
    assert set(MANUAL_EXIT_REASONS) == {"shrinkage", "sample", "reprocessing", "transfer", "other"}
