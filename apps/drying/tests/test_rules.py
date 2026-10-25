from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.drying.rules import available_hours, compute_yield, day_number

BOGOTA = ZoneInfo("America/Bogota")
# Un secado iniciado a media tarde, como el del ejemplo: el 22 de octubre a las 14:00.
START = datetime(2026, 10, 22, 14, 0, tzinfo=BOGOTA)
LATER = START + timedelta(days=10)


# --- Día de secado ---


def test_the_day_of_the_start_is_day_one_even_in_the_afternoon():
    assert day_number(date(2026, 10, 22), START) == 1


def test_the_days_are_counted_by_date():
    assert day_number(date(2026, 10, 24), START) == 3


def test_a_day_without_a_log_still_counts():
    # Sin bitácora el 23, la del 24 sigue siendo el día 3.
    assert day_number(date(2026, 10, 24), START) - day_number(date(2026, 10, 22), START) == 2


def test_the_date_is_the_local_one_in_bogota():
    # Las 21:00 en Bogotá ya son el día siguiente en UTC; el día de secado es el de Bogotá.
    evening = datetime(2026, 10, 22, 21, 0, tzinfo=BOGOTA)

    assert day_number(date(2026, 10, 23), evening) == 2


# --- Horas de un día dentro del secado ---


def test_the_first_day_counts_from_the_start_time():
    assert available_hours(date(2026, 10, 22), START, LATER) == Decimal("10.0")


def test_a_full_day_has_24_hours():
    assert available_hours(date(2026, 10, 23), START, LATER) == Decimal("24.0")


def test_today_counts_until_now():
    now = datetime(2026, 10, 24, 9, 30, tzinfo=BOGOTA)

    assert available_hours(date(2026, 10, 24), START, now) == Decimal("9.5")


def test_the_day_of_the_start_counts_until_now_if_it_is_still_that_day():
    now = datetime(2026, 10, 22, 16, 15, tzinfo=BOGOTA)

    assert available_hours(date(2026, 10, 22), START, now) == Decimal("2.3")


@pytest.mark.parametrize("log_date", [date(2026, 10, 21), date(2026, 11, 5)])
def test_a_date_outside_the_drying_has_no_hours(log_date):
    assert available_hours(log_date, START, LATER) == Decimal("0.0")


# --- Rendimiento ---


def test_the_yield_is_the_dry_weight_over_the_green_weight():
    assert compute_yield(Decimal("313.2"), Decimal("820.0")) == Decimal("38.2")


@pytest.mark.parametrize(
    ("dry", "green", "expected"),
    [
        ("100.0", "100.0", "100.0"),
        ("0.1", "1000.0", "0.0"),
        # 1/8 son 12,5 %: con un decimal se queda; 1/16 son 6,25 %, que sube a 6,3.
        ("1.0", "8.0", "12.5"),
        ("1.0", "16.0", "6.3"),
    ],
)
def test_the_yield_has_one_decimal_rounded_half_up(dry, green, expected):
    assert compute_yield(Decimal(dry), Decimal(green)) == Decimal(expected)
