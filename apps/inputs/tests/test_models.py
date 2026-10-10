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


def test_a_package_needs_its_size_and_a_size_needs_its_package():
    with pytest.raises(ValidationError) as no_size:
        clean(build(package_type="tub"))
    with pytest.raises(ValidationError) as no_type:
        clean(build(package_size=Decimal("100")))

    assert "package_size" in no_size.value.message_dict
    assert "package_type" in no_type.value.message_dict


@pytest.mark.parametrize("size", ["0", "0.0009", "100000.001"])
def test_the_package_size_must_be_between_0_001_and_100000(size):
    with pytest.raises(ValidationError) as error:
        clean(build(package_type="tub", package_size=Decimal(size)))

    assert "package_size" in error.value.message_dict


@pytest.mark.parametrize("size", ["0.001", "3.785", "100000"])
def test_a_package_accepts_the_limits_and_three_decimals(size):
    clean(build(package_type="gallon", package_size=Decimal(size)))


def test_a_package_type_outside_the_options_is_rejected():
    with pytest.raises(ValidationError) as error:
        clean(build(package_type="pallet", package_size=Decimal("1")))

    assert "package_type" in error.value.message_dict


def test_the_unit_cannot_be_a_bag_anymore():
    with pytest.raises(ValidationError) as error:
        clean(build(unit="bag"))

    assert "unit" in error.value.message_dict


def test_the_database_requires_the_package_type_and_size_together():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalInputFactory(package_type="tub")
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalInputFactory(package_size=Decimal("100"))


def test_the_database_rejects_a_package_size_out_of_range():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalInputFactory(package_type="tub", package_size=Decimal("100000.5"))


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
