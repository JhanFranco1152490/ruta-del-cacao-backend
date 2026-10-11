from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from apps.activities.choices import ActivityStatus
from apps.activities.state import (
    OVERDUE_AFTER_DAYS,
    ActivityState,
    activity_state,
    can_complete,
    can_delete,
    can_edit,
    today_in_bogota,
)

SCHEDULED_ON = date(2026, 10, 20)


def scheduled(on=SCHEDULED_ON):
    return SimpleNamespace(status=ActivityStatus.SCHEDULED, scheduled_date=on)


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 18), (ActivityState.SCHEDULED, 0)),
        (date(2026, 10, 20), (ActivityState.SCHEDULED, 0)),
        (date(2026, 10, 21), (ActivityState.DELAYED, 1)),
        (date(2026, 10, 22), (ActivityState.DELAYED, 2)),
        (date(2026, 10, 23), (ActivityState.OVERDUE, 3)),
        (date(2026, 11, 2), (ActivityState.OVERDUE, 13)),
    ],
    ids=["before", "on-the-day", "one-day-late", "two-days-late", "third-day", "much-later"],
)
def test_the_state_follows_the_days_since_the_scheduled_date(today, expected):
    assert activity_state(scheduled(), today) == expected


def test_the_tolerance_is_three_days():
    assert OVERDUE_AFTER_DAYS == 3


def test_a_done_activity_is_done_whatever_its_date():
    activity = SimpleNamespace(status=ActivityStatus.DONE, scheduled_date=date(2026, 1, 1))

    assert activity_state(activity, date(2026, 10, 20)) == (ActivityState.DONE, 0)


def test_today_is_the_date_in_bogota_not_in_utc():
    # A las 23:30 del 20 en Bogotá ya es el 21 en UTC; la actividad todavía no está retrasada.
    late_evening = datetime(2026, 10, 21, 4, 30, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 10, 21, 5, 0, tzinfo=timezone.utc)

    assert today_in_bogota(late_evening) == date(2026, 10, 20)
    assert today_in_bogota(after_midnight) == date(2026, 10, 21)
    assert activity_state(scheduled(), today_in_bogota(late_evening))[0] == ActivityState.SCHEDULED
    assert activity_state(scheduled(), today_in_bogota(after_midnight))[0] == ActivityState.DELAYED


@pytest.mark.parametrize(
    "state, editable, deletable, completable",
    [
        (ActivityState.SCHEDULED, True, True, True),
        (ActivityState.DELAYED, True, True, True),
        (ActivityState.OVERDUE, False, False, True),
        (ActivityState.DONE, False, False, False),
    ],
)
def test_what_each_state_allows(state, editable, deletable, completable):
    assert can_edit(state) is editable
    assert can_delete(state) is deletable
    assert can_complete(state) is completable
