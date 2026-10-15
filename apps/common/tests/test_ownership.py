import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.common.ownership import owner_filter, owns, reaches_all_farms, reaches_farm
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_the_technical_account_is_not_restricted_to_a_producer():
    superuser = UserFactory(is_superuser=True)

    assert owner_filter(superuser) == {}
    assert owner_filter(superuser, "farm__producer_id") == {}
    assert owns(superuser, ProducerFactory().id) is True


def test_a_producer_is_restricted_to_its_own():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    assert owner_filter(owner) == {"producer_id": producer.id}
    assert owner_filter(owner, "farm__producer_id") == {"farm__producer_id": producer.id}
    assert owns(owner, producer.id) is True
    assert owns(owner, ProducerFactory().id) is False


def test_an_account_without_a_producer_owns_nothing():
    assert owns(UserFactory(), ProducerFactory().id) is False


# --- La finca de un empleado ---


def test_a_producer_reaches_every_farm_of_its_own():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    farm = FarmFactory(producer=producer)

    assert reaches_all_farms(owner) is True
    assert reaches_farm(owner, farm.pk) is True
    # Sin restricción de finca: solo la de productor.
    assert owner_filter(owner, "farm__producer_id", farm="farm_id") == {
        "farm__producer_id": producer.id
    }


def test_an_employee_reaches_only_the_farm_it_works_in():
    producer = ProducerFactory()
    farm, other = FarmFactory(producer=producer), FarmFactory(producer=producer)
    employee = make_delegate(producer, ["plots.view_plot"], farm=farm)

    assert reaches_all_farms(employee) is False
    assert reaches_farm(employee, farm.pk) is True
    assert reaches_farm(employee, other.pk) is False
    scope = owner_filter(employee, "farm__producer_id", farm="farm_id")
    assert scope["farm__producer_id"] == producer.id
    assert set(scope["farm_id__in"].values_list("pk", flat=True)) == {farm.pk}


def test_an_employee_without_a_farm_reaches_none():
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    employee = make_delegate(producer, ["plots.view_plot"])

    assert reaches_farm(employee, farm.pk) is False
    # La lista de sus fincas está vacía: no encuentra nada.
    assert not Farm.objects.filter(**owner_filter(employee, farm="id")).exists()


def test_what_does_not_hang_from_a_farm_is_not_restricted_by_it():
    producer = ProducerFactory()
    employee = make_delegate(producer, ["plots.view_plot"], farm=FarmFactory(producer=producer))

    assert owner_filter(employee) == {"producer_id": producer.id}


def test_the_technical_account_reaches_every_farm():
    superuser = UserFactory(is_superuser=True)

    assert reaches_all_farms(superuser) is True
    assert owner_filter(superuser, "farm__producer_id", farm="farm_id") == {}


def test_an_employee_of_several_farms_reaches_all_of_them():
    producer = ProducerFactory()
    first, second = FarmFactory(producer=producer), FarmFactory(producer=producer)
    third = FarmFactory(producer=producer)
    employee = make_delegate(producer, ["plots.view_plot"], farms=[first, second])

    reached = Farm.objects.filter(**owner_filter(employee, farm="id"))

    assert set(reached) == {first, second}
    assert reaches_farm(employee, third.pk) is False
