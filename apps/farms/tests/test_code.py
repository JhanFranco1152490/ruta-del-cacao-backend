"""El código consecutivo de cada finca dentro de su productor (`F01`, `F02`...)."""

import uuid

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.models import Farm
from apps.farms.services import create_farm, delete_farm
from apps.farms.tests.factories import FarmFactory, farm_data
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


def codes_of(producer):
    return sorted(Farm.objects.filter(producer=producer).values_list("number", flat=True))


def test_farms_of_a_producer_get_consecutive_codes(owner):
    first, _ = create_farm(owner, farm_data(name="Uno"))
    second, _ = create_farm(owner, farm_data(name="Dos"))

    assert (first.code, second.code) == ("F01", "F02")


def test_each_producer_counts_its_own_farms(owner):
    other = UserFactory(producer=ProducerFactory())

    create_farm(owner, farm_data(name="Uno"))
    farm, _ = create_farm(other, farm_data(name="Uno"))

    assert farm.code == "F01"


def test_a_deleted_farm_does_not_free_its_code(owner):
    create_farm(owner, farm_data(name="Uno"))
    mistaken, _ = create_farm(owner, farm_data(name="Dos"))
    delete_farm(owner, mistaken.pk, mistaken.version)

    farm, _ = create_farm(owner, farm_data(name="Tres"))

    assert farm.code == "F03"


def test_a_resent_farm_does_not_use_another_number(owner):
    data = farm_data(id=uuid.uuid4())
    create_farm(owner, dict(data))

    _, created = create_farm(owner, dict(data))
    farm, _ = create_farm(owner, farm_data(name="Otra"))

    assert created is False
    assert farm.code == "F02"


def test_a_rejected_farm_does_not_use_a_number(owner):
    create_farm(owner, farm_data(name="Uno"))

    with pytest.raises(Exception):  # noqa: B017 - nombre repetido
        create_farm(owner, farm_data(name="uno"))
    farm, _ = create_farm(owner, farm_data(name="Dos"))

    assert farm.code == "F02"


def test_the_hundredth_farm_has_a_three_digit_code(owner):
    owner.producer.farm_sequence = 99
    owner.producer.save()

    farm, _ = create_farm(owner, farm_data())

    assert farm.code == "F100"


def test_the_code_is_never_edited_by_the_factory_either():
    farm = FarmFactory()

    assert farm.number == 1
    assert FarmFactory(producer=farm.producer).number == 2


@pytest.mark.django_db(transaction=True)
def test_simultaneous_farms_of_a_producer_get_different_codes():
    owner = UserFactory(producer=ProducerFactory())

    run_in_parallel(lambda n: create_farm(owner, farm_data(name=f"Finca {n}")), [1, 2, 3, 4])

    assert codes_of(owner.producer) == [1, 2, 3, 4]
    owner.producer.refresh_from_db()
    assert owner.producer.farm_sequence == 4
