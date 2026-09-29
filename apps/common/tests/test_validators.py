from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.common.municipalities import list_municipalities, validate_municipality_code
from apps.common.validators import (
    strip_document_separators,
    validate_document_digits,
    validate_not_future,
    validate_phone,
    validate_producer_document,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1.090-123 456", "1090123456"), (" 900.123.456-7 ", "9001234567"), ("12345", "12345")],
)
def test_strip_document_separators(raw, expected):
    assert strip_document_separators(raw) == expected


@pytest.mark.parametrize("value", ["1", "1" * 15])
def test_document_digits_accepts_one_to_fifteen_digits(value):
    validate_document_digits(value)


@pytest.mark.parametrize("value", ["", "1" * 16, "10A0123456", "١٢٣", "１２３", "123\n"])
def test_document_digits_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_document_digits(value)


@pytest.mark.parametrize("value", ["001234", "1" * 15])
def test_producer_document_accepts_six_to_fifteen_digits(value):
    validate_producer_document(value)


@pytest.mark.parametrize(
    "value", ["12345", "1" * 16, "12.345-ABC", "١٢٣٤٥٦", "１２３４５６", "123456\n"]
)
def test_producer_document_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_producer_document(value)


@pytest.mark.parametrize("value", ["3001234", "3001234567"])
def test_phone_accepts_seven_to_ten_digits(value):
    validate_phone(value)


@pytest.mark.parametrize(
    "value", ["300123", "30012345678", "300 123 4567", "٣٠٠١٢٣٤٥٦٧", "3001234567\n"]
)
def test_phone_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        validate_phone(value)


def test_not_future_accepts_today_and_rejects_tomorrow():
    validate_not_future(timezone.localdate())
    with pytest.raises(ValidationError):
        validate_not_future(timezone.localdate() + timedelta(days=1))


def test_municipality_code_must_belong_to_norte_de_santander():
    validate_municipality_code("54001")
    with pytest.raises(ValidationError):
        validate_municipality_code("05001")


def test_municipalities_are_sorted_ignoring_accents():
    municipalities = list_municipalities()

    assert len(municipalities) == 40
    assert municipalities[0] == {"code": "54003", "name": "Ábrego"}
