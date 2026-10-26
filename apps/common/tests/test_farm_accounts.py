"""Las cuentas que alcanzan una finca con un permiso, probadas con dos permisos distintos para
dejar claro que solo cambia el permiso."""

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.common.contracts.schedulers import FarmAccounts, Schedulers
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

TURNS = "fermentation.log_turns"
DRYING = "drying.log_drying"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer)


def on_farm(permission, farm):
    return FarmAccounts({farm.producer_id}, permission).on_farm(farm.producer_id, farm.pk)


@pytest.mark.parametrize("permission", [TURNS, DRYING])
def test_only_who_has_the_permission_is_found(producer, farm, permission):
    allowed = make_delegate(producer, [permission], farm=farm)
    make_delegate(producer, ["lots.view_lot"], farm=farm)

    assert on_farm(permission, farm) == {allowed.pk}


def test_the_permission_of_one_stage_does_not_serve_another(producer, farm):
    turner = make_delegate(producer, [TURNS], farm=farm)

    assert turner.pk in on_farm(TURNS, farm)
    assert turner.pk not in on_farm(DRYING, farm)


def test_an_employee_is_found_only_on_the_farms_they_work_in(producer, farm):
    other, third = FarmFactory(producer=producer), FarmFactory(producer=producer)
    worker = make_delegate(producer, [TURNS], farms=[farm, other])

    assert worker.pk in on_farm(TURNS, farm)
    assert worker.pk in on_farm(TURNS, other)
    assert worker.pk not in on_farm(TURNS, third)


def test_an_employee_of_all_farms_is_found_also_on_a_farm_registered_later(producer, farm):
    worker = make_delegate(producer, [TURNS], all_farms=True)
    later = FarmFactory(producer=producer)

    assert worker.pk in on_farm(TURNS, farm)
    assert worker.pk in on_farm(TURNS, later)


def test_an_employee_without_farms_is_found_nowhere(producer, farm):
    make_delegate(producer, [TURNS])

    assert on_farm(TURNS, farm) == set()


def test_the_producer_and_the_foreman_are_found_by_their_roles(producer, farm):
    owner = make_producer_owner(producer)
    foreman = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))

    for permission in (TURNS, DRYING):
        assert on_farm(permission, farm) == {owner.pk, foreman.pk}


def test_inactive_and_superuser_accounts_are_left_out(producer, farm):
    inactive = make_delegate(producer, [TURNS], farm=farm)
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])
    superuser = make_delegate(producer, [TURNS], farm=farm)
    superuser.is_superuser = True
    superuser.save(update_fields=["is_superuser"])

    assert on_farm(TURNS, farm) == set()


def test_the_accounts_of_another_producer_are_left_out(producer, farm):
    other = ProducerFactory()
    make_delegate(other, [TURNS], all_farms=True)

    assert on_farm(TURNS, farm) == set()


def test_the_farms_of_an_account_add_no_queries(producer, django_assert_max_num_queries):
    farms = [FarmFactory(producer=producer) for _ in range(5)]
    make_producer_owner(producer)
    make_delegate(producer, [TURNS], farms=farms)

    # Las cuentas, sus fincas y, por cada cuenta, si es empleado: crece con las cuentas, nunca con
    # las fincas.
    with django_assert_max_num_queries(2 + 2):
        accounts = FarmAccounts({producer.pk}, TURNS)
    for farm in farms:
        assert len(accounts.on_farm(producer.pk, farm.pk)) == 2


def test_no_producers_need_no_queries(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert FarmAccounts(set(), TURNS).on_farm(1, 1) == set()


def test_schedulers_are_the_accounts_that_can_schedule(producer, farm):
    scheduler = make_delegate(producer, ["activities.add_agriculturalactivity"], farm=farm)
    make_delegate(producer, [TURNS], farm=farm)

    found = Schedulers({producer.pk}).on_farm(producer.pk, farm.pk)

    assert found == {scheduler.pk}
