from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.common.figures import code_order, one_decimal, percentage, quality_split, sum_by


def test_one_decimal_rounds_half_up():
    assert one_decimal(Decimal("10.25")) == Decimal("10.3")
    assert one_decimal(Decimal("10.24")) == Decimal("10.2")
    assert one_decimal(Decimal("0")) == Decimal("0.0")


def test_percentage_rounds_each_one_on_its_own():
    assert percentage(Decimal("290.0"), Decimal("380.0")) == Decimal("76.3")
    assert percentage(Decimal("1"), Decimal("3")) == Decimal("33.3")


@pytest.mark.parametrize("total", [Decimal("0"), Decimal("0.0")])
def test_percentage_of_nothing_is_null_and_not_zero(total):
    assert percentage(Decimal("0"), total) is None


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


def test_codes_order_by_their_number_and_not_as_text():
    assert sorted(["F100", "F02", "F99", "F10"], key=code_order) == ["F02", "F10", "F99", "F100"]


def test_sum_by_groups_and_leaves_out_the_keys_that_do_not_appear():
    rows = [
        SimpleNamespace(farm="a", kg=Decimal("1.5")),
        SimpleNamespace(farm="b", kg=Decimal("2.0")),
        SimpleNamespace(farm="a", kg=Decimal("3.0")),
    ]

    assert sum_by(rows, "farm", "kg") == {"a": Decimal("4.5"), "b": Decimal("2.0")}
