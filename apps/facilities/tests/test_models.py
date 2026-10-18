from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.facilities.models import MAX_CAPACITY_KG, PostharvestFacility
from apps.farms.tests.factories import FarmFactory

from .factories import PostharvestFacilityFactory

pytestmark = pytest.mark.django_db


def build(**fields):
    fields.setdefault("farm", FarmFactory())
    fields.setdefault("facility_type", PostharvestFacility.FacilityType.FERMENTATION_BOX)
    fields.setdefault("name", "C-04")
    fields.setdefault("capacity_kg", 600)
    return PostharvestFacility(**fields)


def clean(facility):
    facility.full_clean(validate_unique=False, validate_constraints=False)
    return facility


def test_a_new_facility_is_active():
    assert build().is_active is True


def test_clean_trims_and_normalizes_the_name():
    facility = clean(build(name=" C-02 "))

    assert facility.name == "C-02"
    assert facility.name_normalized == clean(build(name="c 02")).name_normalized


@pytest.mark.parametrize("name", ["", "   ", " - ", "x" * 41])
def test_a_name_without_content_or_over_40_characters_is_rejected(name):
    with pytest.raises(ValidationError) as error:
        clean(build(name=name))

    assert "name" in error.value.message_dict


def test_a_one_character_name_is_accepted():
    assert clean(build(name="A")).name == "A"


@pytest.mark.parametrize("capacity", [0, MAX_CAPACITY_KG + 1, Decimal("12.55")])
def test_the_capacity_is_above_zero_up_to_10000_with_one_decimal(capacity):
    with pytest.raises(ValidationError) as error:
        clean(build(capacity_kg=capacity))

    assert "capacity_kg" in error.value.message_dict


def test_the_capacity_takes_one_decimal():
    assert clean(build(capacity_kg=Decimal("12.5"))).capacity_kg == Decimal("12.5")


@pytest.mark.parametrize("capacity", [0, MAX_CAPACITY_KG + 1])
def test_the_database_rejects_a_capacity_out_of_range(capacity):
    with pytest.raises(IntegrityError), transaction.atomic():
        PostharvestFacilityFactory(capacity_kg=capacity)


def test_the_type_must_be_one_of_its_options():
    with pytest.raises(ValidationError) as error:
        clean(build(facility_type="mechanical_dryer"))

    assert "facility_type" in error.value.message_dict


def test_the_name_is_unique_in_the_farm_regardless_of_the_type():
    existing = PostharvestFacilityFactory(name="C-02")

    with pytest.raises(IntegrityError), transaction.atomic():
        PostharvestFacilityFactory(
            farm=existing.farm,
            name="c 02",
            facility_type=PostharvestFacility.FacilityType.SOLAR_DRYER,
        )


def test_the_same_name_is_allowed_in_another_farm():
    existing = PostharvestFacilityFactory(name="C-02")

    other_farm = FarmFactory(producer=existing.farm.producer)

    other = PostharvestFacilityFactory(farm=other_farm, name="C-02")

    assert other.pk != existing.pk
