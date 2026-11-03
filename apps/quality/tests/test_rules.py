from decimal import Decimal

import pytest

from apps.quality.exceptions import ClassificationSumMismatch, QualitySumExceeds100
from apps.quality.rules import (
    check_classification_total,
    check_percentages_total,
    difference_message,
    discard_reason_errors,
    percentages_total,
)


def test_the_total_adds_the_three_percentages():
    assert percentages_total(Decimal("78.5"), Decimal("2.0"), Decimal("4.5")) == Decimal("85.0")


@pytest.mark.parametrize("other", ["0.0", "5.0"])
def test_a_total_up_to_100_passes(other):
    check_percentages_total(Decimal("80.0"), Decimal("15.0"), Decimal(other))


def test_a_total_above_100_is_refused_with_the_total():
    with pytest.raises(QualitySumExceeds100) as error:
        check_percentages_total(Decimal("80.0"), Decimal("15.0"), Decimal("5.1"))

    assert error.value.extra == {"total_pct": "100.1"}


# --- La clasificación ---


def test_the_classification_passes_when_it_adds_up_exactly():
    check_classification_total(
        Decimal("313.2"), Decimal("200.1"), Decimal("100.0"), Decimal("13.1")
    )


@pytest.mark.parametrize(
    "difference, message",
    [
        (Decimal("13.2"), "Faltan 13,2 kg por distribuir"),
        (Decimal("0.1"), "Faltan 0,1 kg por distribuir"),
        (Decimal("-4.8"), "Sobran 4,8 kg"),
    ],
)
def test_the_difference_is_said_in_kilos_with_a_comma(difference, message):
    assert difference_message(difference) == message


def test_a_classification_that_does_not_add_up_carries_the_three_numbers():
    with pytest.raises(ClassificationSumMismatch) as error:
        check_classification_total(
            Decimal("313.2"), Decimal("250.0"), Decimal("50.0"), Decimal("0.0")
        )

    assert error.value.extra == {
        "expected_kg": "313.2",
        "received_kg": "300.0",
        "difference_kg": "13.2",
    }
    assert error.value.fields == {"non_field_errors": ["Faltan 13,2 kg por distribuir"]}


@pytest.mark.parametrize(
    "discard_kg, reason, detail, errors",
    [
        ("0.0", "", "", {}),
        ("8.0", "mold", "", {}),
        ("8.0", "other", "Granos partidos", {}),
        ("8.0", "", "", {"discard_reason": ["Indique el motivo del descarte"]}),
        ("0.0", "mold", "", {"discard_reason": ["Sin descarte no hay motivo"]}),
        ("8.0", "other", "  ", {"discard_detail": ["Describa el motivo del descarte"]}),
    ],
)
def test_the_reason_goes_with_the_discard(discard_kg, reason, detail, errors):
    assert discard_reason_errors(Decimal(discard_kg), reason, detail) == errors
