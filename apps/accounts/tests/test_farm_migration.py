"""La migración que deja a los empleados que ya existían en su finca. Sus funciones se prueban
con el estado actual de los modelos: solo leen y escriben columnas que no han cambiado desde
entonces."""

from importlib import import_module

import pytest
from django.apps import apps

from apps.accounts.models import Role
from apps.accounts.system_roles import FOREMAN, SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

migration = import_module("apps.accounts.migrations.0016_assign_the_only_farm")
scope_migration = import_module("apps.accounts.migrations.0015_all_farms_and_role_farm_scope")


def foreman_of(producer):
    return grant_role(UserFactory(producer=producer), get_system_role(FOREMAN))


def test_employees_whose_role_takes_one_farm_are_placed_in_the_only_farm():
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    foreman = foreman_of(producer)
    one_farm_role = RoleFactory(producer=producer, farm_scope=Role.FarmScope.ONE)
    other = grant_role(UserFactory(producer=producer), one_farm_role)

    migration.assign_the_only_farm(apps, None)

    foreman.refresh_from_db()
    other.refresh_from_db()
    assert list(foreman.farms.all()) == list(other.farms.all()) == [farm]
    assert not foreman.all_farms


def test_a_role_that_takes_several_farms_is_not_decided_for_the_producer():
    # Un rol propio puede ser el de un administrador de confianza: una finca lo limitaría en
    # silencio cuando se registre otra.
    producer = ProducerFactory()
    FarmFactory(producer=producer)
    delegate = make_delegate(producer, ["plots.view_plot"])

    migration.assign_the_only_farm(apps, None)

    delegate.refresh_from_db()
    assert not delegate.farms.exists()
    assert not delegate.all_farms


def test_with_several_farms_or_none_the_employees_wait_for_the_producer():
    several, none = ProducerFactory(), ProducerFactory()
    FarmFactory.create_batch(2, producer=several)
    waiting = [foreman_of(several), foreman_of(none)]

    migration.assign_the_only_farm(apps, None)

    for employee in waiting:
        employee.refresh_from_db()
        assert not employee.farms.exists()


def test_accounts_that_take_no_farm_are_left_alone():
    producer = ProducerFactory()
    FarmFactory(producer=producer)
    owner = make_producer_owner(producer)
    seller = grant_role(UserFactory(producer=producer), get_system_role(SALES_MANAGER))

    migration.assign_the_only_farm(apps, None)

    for account in (owner, seller):
        account.refresh_from_db()
        assert not account.farms.exists()
        assert not account.all_farms


def test_an_employee_already_in_a_farm_is_not_moved():
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    employee = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))

    migration.assign_the_only_farm(apps, None)

    employee.refresh_from_db()
    assert list(employee.farms.all()) == [farm]


def test_an_employee_with_all_farms_is_not_given_one():
    producer = ProducerFactory()
    FarmFactory(producer=producer)
    employee = grant_role(UserFactory(producer=producer, all_farms=True), get_system_role(FOREMAN))

    migration.assign_the_only_farm(apps, None)

    employee.refresh_from_db()
    assert not employee.farms.exists()
    assert employee.all_farms


def test_undoing_it_releases_every_farm():
    producer = ProducerFactory()
    employee = UserFactory(producer=producer, farm=FarmFactory(producer=producer))

    migration.release_farms(apps, None)

    employee.refresh_from_db()
    assert not employee.farms.exists()


def test_the_foreman_role_takes_one_farm_and_the_others_several():
    Role.objects.filter(code=FOREMAN).update(farm_scope=Role.FarmScope.MANY)

    scope_migration.foreman_is_one_farm(apps, None)

    assert get_system_role(FOREMAN).farm_scope == Role.FarmScope.ONE
    assert get_system_role(SALES_MANAGER).farm_scope == Role.FarmScope.MANY
