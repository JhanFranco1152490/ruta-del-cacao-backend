"""La migración que deja a los empleados que ya existían en su finca. Sus funciones se prueban
con el estado actual de los modelos: solo leen y escriben columnas que no han cambiado desde
entonces."""

from importlib import import_module

import pytest
from django.apps import apps

from apps.accounts.system_roles import FOREMAN, SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

migration = import_module("apps.accounts.migrations.0015_assign_the_only_farm")


def foreman_of(producer):
    return grant_role(UserFactory(producer=producer), get_system_role(FOREMAN))


def test_field_employees_of_a_producer_with_one_farm_are_placed_in_it():
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    foreman = foreman_of(producer)
    delegate = make_delegate(producer, ["plots.view_plot"])

    migration.assign_the_only_farm(apps, None)

    foreman.refresh_from_db()
    delegate.refresh_from_db()
    assert list(foreman.farms.all()) == list(delegate.farms.all()) == [farm]


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
    office = make_delegate(producer, ["accounts.users_view"])

    migration.assign_the_only_farm(apps, None)

    for account in (owner, seller, office):
        account.refresh_from_db()
        assert not account.farms.exists()


def test_an_employee_already_in_a_farm_is_not_moved():
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    employee = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))

    migration.assign_the_only_farm(apps, None)

    employee.refresh_from_db()
    assert list(employee.farms.all()) == [farm]


def test_undoing_it_releases_every_farm():
    producer = ProducerFactory()
    employee = UserFactory(producer=producer, farm=FarmFactory(producer=producer))

    migration.release_farms(apps, None)

    employee.refresh_from_db()
    assert not employee.farms.exists()
