import threading

import pytest
from django.db import connections, transaction
from rest_framework.exceptions import ValidationError

from apps.accounts.authorization import (
    ACCOUNT_KIND_ADMINISTRATOR,
    ACCOUNT_KIND_EMPLOYEE,
    ACCOUNT_KIND_PRODUCER,
    effective_permissions,
    ensure_can_assign_roles,
    ensure_can_grant,
    ensure_can_manage_account,
    ensure_can_manage_role,
    ensure_not_last_administrator,
    ensure_not_self,
    ensure_valid_role_set,
)
from apps.accounts.exceptions import (
    ExceedsOwnPermissions,
    LastAdministrator,
    RoleImmutable,
    SelfModification,
)
from apps.accounts.system_roles import (
    ADMINISTRATOR,
    FOREMAN,
    PRODUCER,
    QUALITY_MANAGER,
    get_system_role,
)
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


# --- effective_permissions -------------------------------------------------------------------


def test_effective_permissions_reflects_the_roles_held():
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view", "accounts.users_create"])

    assert effective_permissions(delegate) == {"accounts.users_view", "accounts.users_create"}


def test_superuser_effective_permissions_include_everything():
    superuser = UserFactory(is_superuser=True)

    assert "accounts.roles_manage" in effective_permissions(superuser)


# --- ensure_can_grant (regla "conceder") -------------------------------------------------------


def test_ensure_can_grant_exempts_the_superuser():
    ensure_can_grant(UserFactory(is_superuser=True), ["producers.view", "unknown.code"])


def test_ensure_can_grant_rejects_a_non_delegable_code_even_if_the_actor_has_it():
    admin = make_administrator()

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_grant(admin, ["producers.view"])


def test_ensure_can_grant_rejects_a_delegable_code_the_actor_lacks():
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view"])

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_grant(delegate, ["accounts.roles_manage"])


def test_ensure_can_grant_allows_a_delegable_code_the_actor_has():
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view"])

    ensure_can_grant(delegate, ["accounts.users_view"])


# --- ensure_valid_role_set ---------------------------------------------------------------------


def test_ensure_valid_role_set_rejects_an_empty_set():
    with pytest.raises(ValidationError):
        ensure_valid_role_set([])


def test_ensure_valid_role_set_rejects_administrator_combined_with_another_role():
    with pytest.raises(ValidationError):
        ensure_valid_role_set([get_system_role(ADMINISTRATOR), get_system_role(FOREMAN)])


def test_ensure_valid_role_set_allows_administrator_alone():
    ensure_valid_role_set([get_system_role(ADMINISTRATOR)])


def test_ensure_valid_role_set_allows_several_non_exclusive_roles():
    ensure_valid_role_set([get_system_role(FOREMAN), get_system_role(QUALITY_MANAGER)])


# --- ensure_can_assign_roles (regla "asignar") --------------------------------------------------


def test_ensure_can_assign_roles_administrator_kind_requires_the_administrator_role():
    owner = make_producer_owner(ProducerFactory())

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_assign_roles(
            owner,
            [get_system_role(ADMINISTRATOR)],
            target_producer_id=None,
            account_kind=ACCOUNT_KIND_ADMINISTRATOR,
        )


def test_ensure_can_assign_roles_administrator_kind_allows_an_administrator():
    admin = make_administrator()

    ensure_can_assign_roles(
        admin,
        [get_system_role(ADMINISTRATOR)],
        target_producer_id=None,
        account_kind=ACCOUNT_KIND_ADMINISTRATOR,
    )


def test_ensure_can_assign_roles_producer_kind_requires_the_administrator_role():
    producer = ProducerFactory()

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_assign_roles(
            UserFactory(),
            [get_system_role(PRODUCER)],
            target_producer_id=producer.id,
            account_kind=ACCOUNT_KIND_PRODUCER,
        )
    ensure_can_assign_roles(
        make_administrator(),
        [get_system_role(PRODUCER)],
        target_producer_id=producer.id,
        account_kind=ACCOUNT_KIND_PRODUCER,
    )


def test_ensure_can_assign_roles_employee_kind_rejects_fixed_roles():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_assign_roles(
            owner,
            [get_system_role(ADMINISTRATOR)],
            target_producer_id=producer.id,
            account_kind=ACCOUNT_KIND_EMPLOYEE,
        )


def test_ensure_can_assign_roles_employee_kind_rejects_a_role_the_actor_lacks():
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view"])
    stronger_role = RoleFactory(producer=producer, permissions=["accounts.roles_manage"])

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_assign_roles(
            delegate,
            [stronger_role],
            target_producer_id=producer.id,
            account_kind=ACCOUNT_KIND_EMPLOYEE,
        )


def test_ensure_can_assign_roles_employee_kind_rejects_a_role_from_another_producer():
    producer = ProducerFactory()
    other_producer = ProducerFactory()
    owner = make_producer_owner(producer)
    foreign_role = RoleFactory(producer=other_producer)

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_assign_roles(
            owner,
            [foreign_role],
            target_producer_id=producer.id,
            account_kind=ACCOUNT_KIND_EMPLOYEE,
        )


def test_ensure_can_assign_roles_employee_kind_allows_predefined_and_own_custom_roles():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    own_role = RoleFactory(producer=producer)

    ensure_can_assign_roles(
        owner,
        [get_system_role(FOREMAN), own_role],
        target_producer_id=producer.id,
        account_kind=ACCOUNT_KIND_EMPLOYEE,
    )


def test_ensure_can_assign_roles_administrator_cannot_assign_roles_for_employees():
    admin = make_administrator()
    producer = ProducerFactory()
    role = get_system_role(FOREMAN)

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_assign_roles(
            admin, [role], target_producer_id=producer.id, account_kind=ACCOUNT_KIND_EMPLOYEE
        )


def test_superuser_assigns_roles_for_the_employees_of_any_producer():
    superuser = UserFactory(is_superuser=True)
    producer = ProducerFactory()

    ensure_can_assign_roles(
        superuser,
        [get_system_role(FOREMAN)],
        target_producer_id=producer.id,
        account_kind=ACCOUNT_KIND_EMPLOYEE,
    )


# --- ensure_can_manage_account (regla "administrar") --------------------------------------------


def test_a_delegate_cannot_reach_the_producer_account():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    delegate = make_delegate(
        producer,
        [
            "accounts.users_view",
            "accounts.users_create",
            "accounts.users_update",
            "accounts.users_change_status",
            "accounts.roles_view",
            "accounts.roles_manage",
        ],
    )

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_account(delegate, owner)


def test_a_delegate_with_every_permission_of_the_producer_still_cannot_reach_their_account():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    delegate = make_delegate(producer, sorted(get_system_role(PRODUCER).permission_codes))

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_account(delegate, owner)


def test_a_delegate_cannot_manage_a_peer_with_more_permissions():
    producer = ProducerFactory()
    strong = make_delegate(producer, ["accounts.users_view", "accounts.roles_manage"])
    weak = make_delegate(producer, ["accounts.users_view"])

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_account(weak, strong)


def test_a_delegate_can_manage_a_plain_employee():
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view"])
    employee = UserFactory(producer=producer)

    ensure_can_manage_account(delegate, employee)


def test_a_producer_cannot_manage_another_producers_employee():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    other_employee = UserFactory(producer=ProducerFactory())

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_account(owner, other_employee)


def test_administrator_always_reaches_the_producer_account():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    admin = make_administrator()

    ensure_can_manage_account(admin, owner)


def test_administrator_always_reaches_another_administrator_account():
    admin = make_administrator()
    other_admin = make_administrator()

    ensure_can_manage_account(admin, other_admin)


def test_administrator_cannot_manage_an_employee():
    producer = ProducerFactory()
    employee = UserFactory(producer=producer)
    admin = make_administrator()

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_account(admin, employee)


def test_superuser_reaches_anyone():
    someone = UserFactory(producer=ProducerFactory())

    ensure_can_manage_account(UserFactory(is_superuser=True), someone)


# --- ensure_can_manage_role ----------------------------------------------------------------------


def test_a_fixed_or_predefined_role_is_immutable_even_for_the_superuser():
    superuser = UserFactory(is_superuser=True)

    with pytest.raises(RoleImmutable):
        ensure_can_manage_role(superuser, get_system_role(ADMINISTRATOR))
    with pytest.raises(RoleImmutable):
        ensure_can_manage_role(superuser, get_system_role(FOREMAN))


def test_a_delegate_cannot_manage_a_role_with_permissions_it_lacks():
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view"])
    stronger_role = RoleFactory(producer=producer, permissions=["accounts.roles_manage"])

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_role(delegate, stronger_role)


def test_a_producer_cannot_manage_another_producers_role():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    foreign_role = RoleFactory(producer=ProducerFactory())

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_role(owner, foreign_role)


def test_administrator_cannot_manage_a_role():
    producer = ProducerFactory()
    role = RoleFactory(producer=producer)
    admin = make_administrator()

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_manage_role(admin, role)


def test_superuser_manages_the_custom_role_of_any_producer():
    role = RoleFactory(producer=ProducerFactory())

    ensure_can_manage_role(UserFactory(is_superuser=True), role)


# --- ensure_not_self ---------------------------------------------------------------------------


def test_ensure_not_self_rejects_the_same_account():
    user = UserFactory()

    with pytest.raises(SelfModification):
        ensure_not_self(user, user)


def test_ensure_not_self_allows_two_different_accounts():
    ensure_not_self(UserFactory(), UserFactory())


# --- ensure_not_last_administrator ---------------------------------------------------------------


def test_rejects_deactivating_the_only_administrator():
    admin = make_administrator()

    with transaction.atomic():
        with pytest.raises(LastAdministrator):
            ensure_not_last_administrator(admin)


def test_allows_deactivating_one_administrator_when_another_remains():
    make_administrator()
    admin = make_administrator()

    with transaction.atomic():
        ensure_not_last_administrator(admin)


@pytest.mark.django_db(transaction=True)
def test_concurrent_deactivations_leave_exactly_one_administrator(system_roles):
    first = make_administrator()
    second = make_administrator()
    barrier = threading.Barrier(2)
    results = {}

    def deactivate(target):
        barrier.wait()
        try:
            with transaction.atomic():
                ensure_not_last_administrator(target)
                target.is_active = False
                target.save(update_fields=["is_active"])
            results[target.pk] = "ok"
        except LastAdministrator:
            results[target.pk] = "rejected"
        finally:
            # Cada hilo abre su propia conexión (no se comparten entre hilos); sin cerrarla,
            # sigue viva cuando pytest-django intenta borrar la base de pruebas al terminar.
            connections.close_all()

    threads = [
        threading.Thread(target=deactivate, args=(first,)),
        threading.Thread(target=deactivate, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results.values()) == ["ok", "rejected"]
