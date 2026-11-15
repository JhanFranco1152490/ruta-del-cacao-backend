from decimal import Decimal

import pytest

from apps.indicators.rules import (
    code_order,
    month_series,
    one_decimal,
    per_hectare,
    percentage,
    quality_split,
)


def test_one_decimal_rounds_half_up():
    assert one_decimal(Decimal("10.25")) == Decimal("10.3")
    assert one_decimal(Decimal("10.24")) == Decimal("10.2")
    assert one_decimal(Decimal("0")) == Decimal("0.0")


def test_per_hectare_divides_by_the_declared_area():
    assert per_hectare(Decimal("620.0"), Decimal("2.50")) == Decimal("248.0")
    assert per_hectare(Decimal("100.0"), Decimal("3.00")) == Decimal("33.3")


@pytest.mark.parametrize("area", [Decimal("0"), Decimal("0.00")])
def test_per_hectare_without_area_is_null(area):
    assert per_hectare(Decimal("100.0"), area) is None


def test_percentage_rounds_each_one_on_its_own():
    assert percentage(Decimal("290.0"), Decimal("380.0")) == Decimal("76.3")
    assert percentage(Decimal("1"), Decimal("3")) == Decimal("33.3")


def test_percentage_of_nothing_is_null_and_not_zero():
    assert percentage(Decimal("0"), Decimal("0")) is None


def test_quality_split_adds_the_classified_kg_and_their_shares():
    split = quality_split(Decimal("290.0"), Decimal("70.0"), Decimal("20.0"))

    assert split == {
        "classified_kg": Decimal("380.0"),
        "g1_kg": Decimal("290.0"),
        "g2_kg": Decimal("70.0"),
        "discard_kg": Decimal("20.0"),
        "g1_pct": Decimal("76.3"),
        "g2_pct": Decimal("18.4"),
        "discard_pct": Decimal("5.3"),
    }


def test_quality_split_without_classified_kg_has_null_shares():
    split = quality_split(Decimal("0"), Decimal("0"), Decimal("0"))

    assert split["classified_kg"] == Decimal("0.0")
    assert (split["g1_pct"], split["g2_pct"], split["discard_pct"]) == (None, None, None)


def test_month_series_fills_every_month_with_zeros():
    series = month_series(
        ["2025-12", "2026-01", "2026-02"],
        {"2026-01": {"green_kg": Decimal("7.5")}},
        ("green_kg", "dry_kg"),
    )

    assert series == [
        {"month": "2025-12", "green_kg": Decimal("0.0"), "dry_kg": Decimal("0.0")},
        {"month": "2026-01", "green_kg": Decimal("7.5"), "dry_kg": Decimal("0.0")},
        {"month": "2026-02", "green_kg": Decimal("0.0"), "dry_kg": Decimal("0.0")},
    ]


def test_codes_order_by_their_number_and_not_as_text():
    assert sorted(["F100", "F02", "F99", "F10"], key=code_order) == ["F02", "F10", "F99", "F100"]
