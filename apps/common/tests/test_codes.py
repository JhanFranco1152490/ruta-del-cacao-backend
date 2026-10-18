import pytest

from apps.common.codes import format_code, next_number, number_from_query
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory


def test_a_code_has_at_least_two_digits():
    assert format_code("F", 2) == "F02"
    assert format_code("P", 10) == "P10"


def test_a_code_grows_past_two_digits_without_truncating():
    assert format_code("F", 100) == "F100"
    assert format_code("P", 1234) == "P1234"


@pytest.mark.parametrize(
    ("term", "expected"),
    [("F02", 2), ("f2", 2), (" F 02 ", 2), ("f100", 100), ("2", 2), ("02", 2)],
)
def test_a_query_that_looks_like_a_code_gives_its_number(term, expected):
    assert number_from_query("F", term) == expected


@pytest.mark.parametrize("term", ["", "  ", "La Esperanza", "P02", "F", "F0", "F-2", "F2x"])
def test_any_other_query_gives_no_number(term):
    assert number_from_query("F", term) is None


@pytest.mark.django_db
def test_the_counter_only_goes_up():
    producer = ProducerFactory()

    assert next_number(Producer, producer.pk, "farm_sequence") == 1
    assert next_number(Producer, producer.pk, "farm_sequence") == 2

    producer.refresh_from_db()
    assert producer.farm_sequence == 2
