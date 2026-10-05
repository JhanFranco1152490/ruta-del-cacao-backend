import pytest

from apps.accounts.scope import acts_for_producer, visible_roles, visible_users
from apps.accounts.system_roles import ADMINISTRATOR, PRODUCER
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


# --- visible_users ------------------------------------------------------------------------


def test_superuser_sees_every_account_except_superusers():
    UserFactory(is_superuser=True)
    other_superuser = UserFactory(is_superuser=True)
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    actor = UserFactory(is_superuser=True)

    result = set(visible_users(actor).values_list("id", flat=True))

    assert result == {owner.id, employee.id}
    assert other_superuser.id not in result


def test_administrator_always_sees_administrator_and_producer_accounts():
    admin = make_administrator()
    other_admin = make_administrator()
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    result = set(visible_users(admin).values_list("id", flat=True))

    assert {other_admin.id, owner.id} <= result


def test_administrator_cannot_see_employees():
    admin = make_administrator()
    producer = ProducerFactory()
    make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    result = visible_users(admin)

    assert not result.filter(id=employee.id).exists()


def test_a_producer_only_sees_its_own_accounts():
    producer = ProducerFactory()
    other_producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    other_owner = make_producer_owner(other_producer)
    make_administrator()

    result = set(visible_users(owner).values_list("id", flat=True))

    assert result == {owner.id, employee.id}
    assert other_owner.id not in result


def test_an_account_without_producer_or_administrator_role_sees_nothing():
    stray = UserFactory()
    UserFactory(producer=ProducerFactory())

    assert not visible_users(stray).exists()


# --- visible_roles --------------------------------------------------------------------------


def test_a_producer_sees_system_roles_and_only_its_own_custom_roles():
    producer = ProducerFactory()
    other_producer = ProducerFactory()
    owner = make_producer_owner(producer)
    own_role = RoleFactory(producer=producer)
    other_role = RoleFactory(producer=other_producer)

    codes = set(visible_roles(owner).values_list("code", flat=True))
    ids = set(visible_roles(owner).values_list("id", flat=True))

    assert {ADMINISTRATOR, PRODUCER} <= codes
    assert own_role.id in ids
    assert other_role.id not in ids


def test_administrator_sees_only_system_roles():
    admin = make_administrator()
    own_role = RoleFactory(producer=ProducerFactory())

    roles = visible_roles(admin)

    assert not roles.filter(id=own_role.id).exists()
    assert {ADMINISTRATOR, PRODUCER} <= set(roles.values_list("code", flat=True))


def test_superuser_sees_the_custom_roles_of_every_producer():
    superuser = UserFactory(is_superuser=True)
    role = RoleFactory(producer=ProducerFactory())

    assert visible_roles(superuser).filter(id=role.id).exists()


# --- acts_for_producer -----------------------------------------------------------------------


def test_acts_for_producer_matrix():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee_of_another = UserFactory(producer=ProducerFactory())
    admin = make_administrator()
    superuser = UserFactory(is_superuser=True)

    assert acts_for_producer(owner, producer.id) is True
    assert acts_for_producer(employee_of_another, producer.id) is False
    assert acts_for_producer(admin, producer.id) is False
    assert acts_for_producer(superuser, producer.id) is True
