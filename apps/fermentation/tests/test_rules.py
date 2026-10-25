from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from apps.fermentation.alerts import next_turn_due_at
from apps.fermentation.rules import numbered
from apps.postharvest_parameters.baseline import FERMENTATION_BASELINE

START = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_without_turns_the_first_one_is_due_48_hours_after_the_start():
    assert next_turn_due_at(START, None, FERMENTATION_BASELINE) == START + timedelta(hours=48)


def test_with_turns_the_next_one_is_due_24_hours_after_the_last():
    last = START + timedelta(hours=49)

    assert next_turn_due_at(START, last, FERMENTATION_BASELINE) == last + timedelta(hours=24)


def test_the_hours_to_wait_are_the_ones_the_producer_configured():
    own = replace(FERMENTATION_BASELINE, first_turn_hours=36, next_turn_hours=12)
    last = START + timedelta(hours=40)

    assert next_turn_due_at(START, None, own) == START + timedelta(hours=36)
    assert next_turn_due_at(START, last, own) == last + timedelta(hours=12)


def test_the_turns_are_numbered_by_their_time_not_by_their_order_of_arrival():
    late = SimpleNamespace(turned_at=START + timedelta(hours=48))
    early = SimpleNamespace(turned_at=START + timedelta(hours=24))
    last = SimpleNamespace(turned_at=START + timedelta(hours=72))

    assert numbered([late, last, early]) == [(1, early), (2, late), (3, last)]
    assert numbered([]) == []
