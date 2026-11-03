from decimal import Decimal

import pytest

from apps.quality.exceptions import QualitySumExceeds100
from apps.quality.rules import check_percentages_total, percentages_total


def test_the_total_adds_the_three_percentages():
    assert percentages_total(Decimal("78.5"), Decimal("2.0"), Decimal("4.5")) == Decimal("85.0")


@pytest.mark.parametrize("other", ["0.0", "5.0"])
def test_a_total_up_to_100_passes(other):
    check_percentages_total(Decimal("80.0"), Decimal("15.0"), Decimal(other))


def test_a_total_above_100_is_refused_with_the_total():
    with pytest.raises(QualitySumExceeds100) as error:
        check_percentages_total(Decimal("80.0"), Decimal("15.0"), Decimal("5.1"))

    assert error.value.extra == {"total_pct": "100.1"}
