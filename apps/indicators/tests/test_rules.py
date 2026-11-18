from decimal import Decimal

import pytest

from apps.indicators.rules import month_series, per_hectare


def test_per_hectare_divides_by_the_declared_area():
    assert per_hectare(Decimal("620.0"), Decimal("2.50")) == Decimal("248.0")
    assert per_hectare(Decimal("100.0"), Decimal("3.00")) == Decimal("33.3")


@pytest.mark.parametrize("area", [Decimal("0"), Decimal("0.00")])
def test_per_hectare_without_area_is_null(area):
    assert per_hectare(Decimal("100.0"), area) is None


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
