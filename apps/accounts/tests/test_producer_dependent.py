import pytest
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.accounts.models import AssociationAccess, Role, User
from apps.accounts.producer_dependent import accounts_dependent
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import enable_association_access, make_administrator
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_the_automatic_owner_account_that_never_signed_in_is_not_important():
    # Por la API el correo es obligatorio, así que el alta crea la cuenta del dueño sola.
    producer = ProducerFactory(email="duena@example.com")

    assert accounts_dependent.count(producer) == 1
    assert accounts_dependent.important_record(producer) is None


def test_an_account_that_already_signed_in_is_important():
    producer = ProducerFactory()
    employee = UserFactory(producer=producer)
    employee.last_login = timezone.now()
    employee.save(update_fields=["last_login"])

    reason = accounts_dependent.important_record(producer)

    assert "ya inició sesión" in reason


def test_the_reason_never_carries_personal_data():
    producer = ProducerFactory()
    employee = UserFactory(producer=producer, email="privado@example.com")
    employee.last_login = timezone.now()
    employee.save(update_fields=["last_login"])

    reason = accounts_dependent.important_record(producer)

    assert "privado@example.com" not in reason
    assert employee.identity_document not in reason


def test_deleting_all_removes_accounts_own_roles_and_the_access_row():
    producer = ProducerFactory()
    UserFactory(producer=producer)
    role = RoleFactory(producer=producer)
    group_id = role.group_id
    enable_association_access(producer)

    accounts_dependent.delete_all(producer, make_administrator())

    assert not User.objects.filter(producer=producer).exists()
    assert not Role.objects.filter(producer=producer).exists()
    assert not Group.objects.filter(pk=group_id).exists()
    assert not AssociationAccess.objects.filter(producer=producer).exists()


def test_deleting_all_leaves_other_producers_and_the_association_alone():
    producer = ProducerFactory()
    other = ProducerFactory()
    UserFactory(producer=other)
    other_role = RoleFactory(producer=other)
    administrator = make_administrator()

    accounts_dependent.delete_all(producer, administrator)

    assert User.objects.filter(producer=other).exists()
    assert Role.objects.filter(pk=other_role.pk).exists()
    assert User.objects.filter(pk=administrator.pk).exists()
