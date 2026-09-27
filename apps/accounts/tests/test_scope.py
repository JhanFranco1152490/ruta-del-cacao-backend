import pytest

from apps.accounts.models import AssociationAccess
from apps.accounts.scope import acts_for_producer, visible_roles, visible_users
from apps.accounts.system_roles import ADMINISTRATOR, PRODUCER, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def grant_role(user, role):
    user.groups.add(role.group)
    return user


def make_administrator():
    return grant_role(UserFactory(), get_system_role(ADMINISTRATOR))


def make_producer_owner(producer):
    return grant_role(UserFactory(producer=producer), get_system_role(PRODUCER))


def enable_association_access(producer):
    AssociationAccess.objects.update_or_create(producer=producer, defaults={"enabled": True})


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


def test_administrator_cannot_see_employees_without_association_access():
    admin = make_administrator()
    producer = ProducerFactory()
    make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    result = visible_users(admin)

    assert not result.filter(id=employee.id).exists()


def test_administrator_sees_employees_once_association_access_is_enabled():
    admin = make_administrator()
    producer = ProducerFactory()
    make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    enable_association_access(producer)

    result = visible_users(admin)

    assert result.filter(id=employee.id).exists()


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


def test_administrator_sees_custom_roles_only_from_producers_with_access_enabled():
    admin = make_administrator()
    producer = ProducerFactory()
    allowed_role = RoleFactory(producer=producer)
    blocked_producer = ProducerFactory()
    blocked_role = RoleFactory(producer=blocked_producer)
    enable_association_access(producer)

    ids = set(visible_roles(admin).values_list("id", flat=True))

    assert allowed_role.id in ids
    assert blocked_role.id not in ids


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
    enable_association_access(producer)
    assert acts_for_producer(admin, producer.id) is True
    assert acts_for_producer(superuser, producer.id) is True
