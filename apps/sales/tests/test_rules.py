from decimal import Decimal

import pytest

from apps.sales.rules import line_subtotal


@pytest.mark.parametrize(
    "kilos, price, expected",
    [
        ("150.0", 18500, 2_775_000),
        ("40.0", 15000, 600_000),
        # 224.987,5: la mitad sube al peso siguiente.
        ("12.5", 17999, 224_988),
        # 0,1 × 3 = 0,3: menos de medio peso baja.
        ("0.1", 3, 0),
        # 0,1 × 5 = 0,5: justo la mitad sube.
        ("0.1", 5, 1),
        ("99999.9", 1_000_000, 99_999_900_000),
    ],
)
def test_the_subtotal_is_kilos_by_price_rounded_half_up_to_the_peso(kilos, price, expected):
    assert line_subtotal(Decimal(kilos), price) == expected


def test_the_subtotal_is_an_integer():
    assert isinstance(line_subtotal(Decimal("12.5"), 17999), int)
