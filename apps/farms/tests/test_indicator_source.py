import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.common.contracts.indicators import ScopedFarm, indicator_source
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def scope(actor, **filters):
    return set(indicator_source("farm_scope")(actor, **filters).values_list("pk", flat=True))


@pytest.fixture
def two_producers():
    mine = ProducerFactory()
    farm_a = FarmFactory(producer=mine)
    farm_b = FarmFactory(producer=mine, is_active=False)
    other = FarmFactory()
    return mine, farm_a, farm_b, other


def test_the_producer_reaches_all_its_farms_active_or_not(two_producers):
    mine, farm_a, farm_b, _ = two_producers

    assert scope(make_producer_owner(mine)) == {farm_a.pk, farm_b.pk}


def test_an_employee_reaches_only_the_farms_it_works_on(two_producers):
    mine, farm_a, _, _ = two_producers
    employee = make_delegate(mine, ["indicators.view_producer_indicators"], farm=farm_a)

    assert scope(employee) == {farm_a.pk}


def test_an_employee_without_a_farm_reaches_nothing(two_producers):
    mine, _, _, _ = two_producers

    assert scope(make_delegate(mine, ["indicators.view_producer_indicators"])) == set()


def test_one_farm_narrows_the_scope_and_a_foreign_one_leaves_it_empty(two_producers):
    mine, farm_a, _, other = two_producers
    owner = make_producer_owner(mine)

    assert scope(owner, farm_id=farm_a.pk) == {farm_a.pk}
    assert scope(owner, farm_id=other.pk) == set()


def test_the_technical_account_reaches_everything_or_one_producer(two_producers):
    mine, farm_a, farm_b, other = two_producers
    technical = UserFactory(is_superuser=True)

    assert scope(technical) == {farm_a.pk, farm_b.pk, other.pk}
    assert scope(technical, producer_id=mine.pk) == {farm_a.pk, farm_b.pk}


def test_only_the_technical_account_chooses_a_producer(two_producers):
    mine, farm_a, farm_b, other = two_producers

    assert scope(make_producer_owner(mine), producer_id=other.producer_id) == {
        farm_a.pk,
        farm_b.pk,
    }


def test_the_association_reaches_every_farm_only_when_it_asks_for_all(two_producers):
    _, farm_a, farm_b, other = two_producers
    administrator = make_administrator()

    assert scope(administrator, everyone=True) == {farm_a.pk, farm_b.pk, other.pk}
    # Sin productor propio, el alcance de un productor no le da nada.
    assert scope(administrator) == set()


def test_asking_for_all_does_not_widen_a_producer(two_producers):
    mine, farm_a, farm_b, _ = two_producers

    assert scope(make_producer_owner(mine), everyone=True) == {farm_a.pk, farm_b.pk}


def test_the_farms_come_with_their_code_municipality_and_producer(
    two_producers, django_assert_num_queries
):
    mine, farm_a, _, _ = two_producers

    with django_assert_num_queries(1):
        rows = indicator_source("farms")([farm_a.pk])

    assert rows == [
        ScopedFarm(
            farm_id=farm_a.pk,
            code=farm_a.code,
            name=farm_a.name,
            municipality_code=farm_a.municipality_code,
            producer_id=mine.pk,
            producer_member_code=mine.member_code,
            producer_first_name=mine.first_name,
            producer_last_name=mine.last_name,
        )
    ]
