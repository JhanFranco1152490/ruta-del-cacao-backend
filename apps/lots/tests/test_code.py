from datetime import date

from apps.lots.code import build_lot_code


def test_the_code_says_producer_farm_plot_date_and_sequence():
    code = build_lot_code("PROD-000123", 2, 5, date(2026, 10, 14), 1)

    assert code == "000123-F02-P05-261014-1"


def test_farm_and_plot_numbers_grow_past_two_digits():
    assert build_lot_code("PROD-000123", 100, 5, date(2026, 10, 14), 1) == (
        "000123-F100-P05-261014-1"
    )
    assert build_lot_code("PROD-000123", 2, 123, date(2026, 10, 14), 1) == (
        "000123-F02-P123-261014-1"
    )


def test_the_sequence_has_no_padding_and_can_have_two_digits():
    assert build_lot_code("PROD-000123", 2, 5, date(2026, 10, 14), 10).endswith("-261014-10")


def test_the_date_is_year_month_day_with_two_digits_each():
    assert build_lot_code("PROD-000007", 1, 1, date(2027, 1, 3), 2) == "000007-F01-P01-270103-2"


def test_the_longest_realistic_code_fits_the_column():
    code = build_lot_code("PROD-999999", 9999, 9999, date(2026, 12, 31), 99)

    assert len(code) <= 40
