from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.inputs.models import AgriculturalInput
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


def build(**fields):
    fields.setdefault("producer", ProducerFactory())
    fields.setdefault("name", "Urea 46 %")
    fields.setdefault("input_type", "fertilizer")
    fields.setdefault("unit", "kg")
    return AgriculturalInput(**fields)


def clean(item):
    item.full_clean(validate_unique=False, validate_constraints=False)
    return item


def test_clean_trims_and_normalizes_the_name():
    item = clean(build(name=" Urea 46% "))

    assert item.name == "Urea 46%"
    assert item.name_normalized == clean(build(name="UREA-46%")).name_normalized


@pytest.mark.parametrize("name", ["U", "x" * 81, "", "   ", " - "])
def test_name_outside_2_to_80_characters_or_without_content_is_rejected(name):
    with pytest.raises(ValidationError) as error:
        clean(build(name=name))

    assert "name" in error.value.message_dict


def test_a_bag_needs_its_weight():
    with pytest.raises(ValidationError) as error:
        clean(build(unit="bag"))

    assert "bag_weight_kg" in error.value.message_dict


@pytest.mark.parametrize("weight", ["0", "0.99", "100.01"])
def test_the_weight_of_a_bag_must_be_between_1_and_100(weight):
    with pytest.raises(ValidationError) as error:
        clean(build(unit="bag", bag_weight_kg=Decimal(weight)))

    assert "bag_weight_kg" in error.value.message_dict


@pytest.mark.parametrize("weight", ["1", "50", "100"])
def test_a_bag_accepts_the_limits(weight):
    clean(build(unit="bag", bag_weight_kg=Decimal(weight)))


def test_a_weight_with_another_unit_is_rejected():
    with pytest.raises(ValidationError) as error:
        clean(build(unit="kg", bag_weight_kg=Decimal("50")))

    assert "bag_weight_kg" in error.value.message_dict


def test_the_database_requires_the_weight_exactly_for_bags():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalInputFactory(unit="bag")
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalInputFactory(unit="kg", bag_weight_kg=Decimal("50"))


def test_the_database_rejects_a_weight_out_of_range():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalInputFactory(unit="bag", bag_weight_kg=Decimal("100.50"))


def test_name_and_type_are_unique_per_producer_once_normalized():
    first = AgriculturalInputFactory(name="Urea 46 %", name_normalized="urea46%")

    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalInputFactory(
            producer=first.producer, name="urea46%", name_normalized="urea46%"
        )

    AgriculturalInputFactory(
        producer=first.producer, name_normalized="urea46%", input_type="other"
    )
    AgriculturalInputFactory(name_normalized="urea46%")
