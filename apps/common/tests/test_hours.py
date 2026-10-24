from datetime import UTC, datetime, timedelta
from decimal import Decimal

from apps.common.hours import hours_between

START = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_the_hours_between_two_moments_have_one_decimal_rounded_half_up():
    assert hours_between(START, START + timedelta(hours=52)) == Decimal("52.0")
    assert hours_between(START, START + timedelta(minutes=30)) == Decimal("0.5")
    assert hours_between(START, START + timedelta(hours=2, minutes=3)) == Decimal("2.1")
    assert hours_between(START, START + timedelta(hours=2, minutes=2)) == Decimal("2.0")
