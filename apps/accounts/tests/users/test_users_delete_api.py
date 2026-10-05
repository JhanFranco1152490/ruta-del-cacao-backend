import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.exceptions import LastAdministrator
from apps.accounts.models import AccountManagementEvent, User
from apps.accounts.system_roles import ADMINISTRATOR, FOREMAN, PRODUCER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import csrf_client, login_by_email, open_session
from apps.accounts.tests.role_helpers import (
    enable_association_access,
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.accounts.users.services import delete_account
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

USERS_URL = "/api/users"
DELETED = AccountManagementEvent.EventType.ACCOUNT_DELETED


def user_url(user) -> str:
    return f"{USERS_URL}/{user.pk}"


def delete_as(actor, target):
    return open_session(csrf_client(), actor).delete(user_url(target))


def make_employee(producer, **kwargs):
    return grant_role(UserFactory(producer=producer, **kwargs), get_system_role(FOREMAN))


def signed_in():
    return {"last_login": timezone.now()}


def exists(user) -> bool:
    return User.objects.filter(pk=user.pk).exists()


# --- Quién puede eliminar ------------------------------------------------------------------------


def test_deleting_requires_a_session():
    employee = make_employee(ProducerFactory())

    response = csrf_client().delete(user_url(employee))

    assert response.status_code == 401
    assert exists(employee)


def test_deleting_requires_the_users_delete_permission():
    producer = ProducerFactory()
    viewer = make_delegate(producer, ["accounts.users_view", "accounts.users_change_status"])
    employee = make_employee(producer)

    response = delete_as(viewer, employee)

    assert response.status_code == 403
    assert exists(employee)


def test_a_delegate_with_the_permission_deletes_an_employee():
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view", "accounts.users_delete"])
    employee = make_employee(producer)

    response = delete_as(delegate, employee)

    assert response.status_code == 204
    assert not exists(employee)


def test_an_account_of_another_producer_is_not_found():
    owner = make_producer_owner(ProducerFactory())
    other = make_employee(ProducerFactory())

    response = delete_as(owner, other)

    assert response.status_code == 404
    assert exists(other)


def test_nobody_deletes_their_own_account():
    owner = make_producer_owner(ProducerFactory())

    response = delete_as(owner, owner)

    assert response.status_code == 403
    assert response.data["code"] == "self_modification"
    assert exists(owner)


def test_the_administrator_needs_the_switch_to_delete_an_employee():
    producer = ProducerFactory()
    admin = make_administrator()
    employee = make_employee(producer)

    blocked = delete_as(admin, employee)
    assert blocked.status_code == 404
    assert exists(employee)

    enable_association_access(producer)
    allowed = delete_as(admin, employee)
    assert allowed.status_code == 204
    assert not exists(employee)


# La cuenta Productor se ve pero no se alcanza (403); la de Administrador ni se ve (404).
@pytest.mark.parametrize(("target_role", "expected"), [(PRODUCER, 403), (ADMINISTRATOR, 404)])
def test_a_delegate_does_not_reach_the_producer_or_administrator_accounts(target_role, expected):
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view", "accounts.users_delete"])
    if target_role == PRODUCER:
        target = make_producer_owner(producer)
    else:
        target = make_administrator()

    response = delete_as(delegate, target)

    assert response.status_code == expected
    assert exists(target)


# --- Las tres clases de cuenta ------------------------------------------------------------------


def test_the_administrator_deletes_a_producer_account_that_never_signed_in():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    admin = make_administrator()

    response = delete_as(admin, owner)

    assert response.status_code == 204
    assert not exists(owner)
    assert exists(employee)
    assert not User.objects.filter(producer=producer, groups__role__code=PRODUCER).exists()


def test_a_deleted_producer_account_can_be_created_again_with_the_same_email():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    email = owner.email
    admin = make_administrator()
    assert delete_as(admin, owner).status_code == 204

    response = open_session(csrf_client(), admin).post(
        USERS_URL,
        {
            "email": email,
            "role_ids": [str(get_system_role(PRODUCER).id)],
            "producer_id": str(producer.id),
        },
        format="json",
    )

    assert response.status_code == 201
    assert User.objects.filter(email=email, producer=producer).exists()


def test_an_administrator_that_never_signed_in_is_deleted_by_another_one():
    first = make_administrator()
    second = make_administrator()

    response = delete_as(first, second)

    assert response.status_code == 204
    assert not exists(second)


def test_the_last_active_administrator_is_not_deleted():
    # Por la API otro administrador activo siempre queda (quien pregunta): el caso real es el de
    # dos administradores que se eliminan a la vez, que cubre la prueba de concurrencia. Aquí se
    # llama al servicio con un actor que ya no está activo.
    only = make_administrator()
    retired = make_administrator()
    retired.is_active = False
    retired.save(update_fields=["is_active"])

    with pytest.raises(LastAdministrator):
        delete_account(retired, only.pk, uuid.uuid4())

    assert exists(only)


# --- El criterio: nunca inició sesión -----------------------------------------------------------


def test_an_account_that_already_signed_in_is_not_deleted():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer, **signed_in())

    response = delete_as(owner, employee)

    assert response.status_code == 409
    assert response.data["code"] == "account_has_activity"
    assert exists(employee)
    assert not AccountManagementEvent.objects.filter(event_type=DELETED).exists()


def test_an_activated_account_that_never_signed_in_is_deleted():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    assert employee.has_usable_password()

    assert delete_as(owner, employee).status_code == 204


def test_the_account_says_whether_it_has_signed_in(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    new = make_employee(producer)
    used = make_employee(producer, **signed_in())
    client = auth_client(owner)

    assert client.get(user_url(new)).data["has_signed_in"] is False
    assert client.get(user_url(used)).data["has_signed_in"] is True


# --- Qué queda ----------------------------------------------------------------------------------


def test_deleting_leaves_an_event_with_only_the_internal_id():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    employee_id = employee.pk
    personal = {employee.email, employee.identity_document, employee.first_name}

    assert delete_as(owner, employee).status_code == 204

    event = AccountManagementEvent.objects.get(event_type=DELETED)
    assert event.actor == owner
    assert event.target_user is None
    assert event.target_user_ref == employee_id
    stored = {str(value) for value in event.__dict__.values()}
    assert not (personal - {""}) & stored


def test_the_earlier_events_of_the_account_stay_with_no_target():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    AccountManagementEvent.objects.create(
        event_type=AccountManagementEvent.EventType.ACCOUNT_CREATED,
        actor=owner,
        target_user=employee,
    )

    assert delete_as(owner, employee).status_code == 204

    created = AccountManagementEvent.objects.get(
        event_type=AccountManagementEvent.EventType.ACCOUNT_CREATED
    )
    assert created.actor == owner
    assert created.target_user is None


def test_the_email_and_document_are_free_after_deleting():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    email, document = employee.email, employee.identity_document
    assert delete_as(owner, employee).status_code == 204

    reused = UserFactory(email=email, identity_document=document, producer=producer)

    assert exists(reused)


def test_deleting_twice_is_a_204_and_then_a_404():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)

    assert delete_as(owner, employee).status_code == 204
    assert delete_as(owner, employee).status_code == 404
    assert AccountManagementEvent.objects.filter(event_type=DELETED).count() == 1


def test_a_deleted_employee_with_an_open_session_gets_a_401():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    employee_client = open_session(csrf_client(), employee)
    assert employee_client.get("/api/auth/me").status_code == 200

    assert delete_as(owner, employee).status_code == 204

    assert employee_client.get("/api/auth/me").status_code == 401


# --- Concurrencia -------------------------------------------------------------------------------


def run_together(calls):
    barrier = Barrier(len(calls))

    def attempt(call):
        try:
            barrier.wait()
            return call()
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        return list(executor.map(attempt, calls))


@pytest.mark.django_db(transaction=True)
def test_two_administrators_deleting_each_other_leave_one(system_roles):
    first = make_administrator()
    second = make_administrator()
    first_client = open_session(csrf_client(), first)
    second_client = open_session(csrf_client(), second)

    responses = run_together(
        [
            lambda: first_client.delete(user_url(second)),
            lambda: second_client.delete(user_url(first)),
        ]
    )

    # La que pierde falla de dos formas, según cuándo la alcance la otra: si llega al servicio,
    # ve que es el último administrador (409); si la otra ya confirmó antes de validar su
    # sesión, esa sesión es de una cuenta que ya no existe (401).
    winner, loser = sorted(responses, key=lambda response: response.status_code)
    assert winner.status_code == 204
    assert (loser.status_code, loser.data["code"]) in {
        (409, "last_administrator"),
        (401, "authentication_failed"),
    }
    assert User.objects.filter(pk__in=[first.pk, second.pk]).count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_deletions_of_the_same_account_leave_one_event(system_roles):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    clients = [open_session(csrf_client(), owner) for _ in range(2)]

    responses = run_together([lambda c=client: c.delete(user_url(employee)) for client in clients])

    assert sorted(response.status_code for response in responses) == [204, 404]
    assert AccountManagementEvent.objects.filter(event_type=DELETED).count() == 1


@pytest.mark.django_db(transaction=True)
def test_signing_in_while_it_is_deleted_never_leaves_a_usable_session(system_roles):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = make_employee(producer)
    owner_client = open_session(csrf_client(), owner)
    login_client = csrf_client()

    login, deletion = run_together(
        [
            lambda: login_by_email(login_client, employee.email),
            lambda: owner_client.delete(user_url(employee)),
        ]
    )

    if exists(employee):
        # El inicio de sesión ganó: la cuenta ya inició sesión y no se elimina.
        assert login.status_code == 200
        assert (deletion.status_code, deletion.data["code"]) == (409, "account_has_activity")
    else:
        assert deletion.status_code == 204
        # Aunque el inicio de sesión alcanzara a responder, esa sesión no sirve de nada.
        assert login_client.get("/api/auth/me").status_code == 401
