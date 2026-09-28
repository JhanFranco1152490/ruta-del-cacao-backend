from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.core import mail
from django.db import connection

from apps.accounts.models import AccountManagementEvent, User
from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import RoleFactory, UserFactory, make_pending_user
from apps.accounts.tests.helpers import csrf_client, open_session
from apps.accounts.tests.roles import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.accounts.throttles import ActivationResendThrottle
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

USERS_URL = "/api/users"


def user_url(user) -> str:
    return f"{USERS_URL}/{user.pk}"


def roles_url(user) -> str:
    return f"{user_url(user)}/roles"


def status_url(user) -> str:
    return f"{user_url(user)}/status"


def resend_url(user) -> str:
    return f"{user_url(user)}/resend-activation"


# --- Editar (PATCH /api/users/{id}) ------------------------------------------------------------


def test_edit_requires_users_update_permission(auth_client):
    producer = ProducerFactory()
    employee = UserFactory(producer=producer)
    viewer = make_delegate(producer, ["accounts.users_view"])

    response = auth_client(viewer).patch(
        user_url(employee), {"phone": "3001234567"}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_a_producer_edits_its_employee(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer, first_name="Antes")

    response = auth_client(owner).patch(
        user_url(employee), {"first_name": "Después"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["first_name"] == "Después"


def test_editing_the_producer_accounts_document_and_names_is_rejected(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    admin = make_administrator()

    response = auth_client(admin).patch(user_url(owner), {"first_name": "Nuevo"}, format="json")

    assert response.status_code == 400
    assert "first_name" in response.data["fields"]


def test_editing_the_producer_accounts_email_is_allowed(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    admin = make_administrator()

    response = auth_client(admin).patch(
        user_url(owner), {"email": "nuevo-correo@example.com"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["email"] == "nuevo-correo@example.com"


def test_cannot_edit_ones_own_account(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).patch(user_url(owner), {"phone": "3001234567"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "self_modification"


def test_a_delegate_cannot_edit_a_peer_with_more_permissions(auth_client):
    producer = ProducerFactory()
    strong = make_delegate(producer, ["accounts.users_view", "accounts.roles_manage"])
    weak = make_delegate(producer, ["accounts.users_view", "accounts.users_update"])

    response = auth_client(weak).patch(user_url(strong), {"phone": "3001234567"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_administrator_can_edit_another_administrator(auth_client):
    admin = make_administrator()
    other_admin = make_administrator()

    response = auth_client(admin).patch(
        user_url(other_admin), {"phone": "3009876543"}, format="json"
    )

    assert response.status_code == 200


def test_edit_requires_at_least_one_field(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    response = auth_client(owner).patch(user_url(employee), {}, format="json")

    assert response.status_code == 400


def test_edit_rejects_unknown_field(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    response = auth_client(owner).patch(user_url(employee), {"is_active": False}, format="json")

    assert response.status_code == 400
    assert "is_active" in response.data["fields"]


def test_edit_rejects_a_duplicate_email(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    UserFactory(email="tomado@example.com")

    response = auth_client(owner).patch(
        user_url(employee), {"email": " Tomado@Example.com "}, format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_email"


def test_changing_email_revokes_the_targets_sessions(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer, email="viejo@example.com")
    employee_client = open_session(csrf_client(), employee)

    response = auth_client(owner).patch(
        user_url(employee), {"email": "nuevo@example.com"}, format="json"
    )

    assert response.status_code == 200
    assert employee_client.post("/api/auth/refresh").status_code == 401


def test_editing_another_producers_account_is_not_found(auth_client):
    owner = make_producer_owner(ProducerFactory())
    other_employee = UserFactory(producer=ProducerFactory())

    response = auth_client(owner).patch(
        user_url(other_employee), {"phone": "3000000000"}, format="json"
    )

    assert response.status_code == 404


# --- Roles (PUT /api/users/{id}/roles) -----------------------------------------------------------


def test_roles_requires_users_update_permission(auth_client):
    producer = ProducerFactory()
    viewer = make_delegate(producer, ["accounts.users_view"])
    employee = UserFactory(producer=producer)
    foreman = get_system_role(FOREMAN)

    response = auth_client(viewer).put(
        roles_url(employee), {"role_ids": [str(foreman.id)]}, format="json"
    )

    assert response.status_code == 403


def test_replace_an_employees_roles(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    foreman = get_system_role(FOREMAN)
    employee = UserFactory(producer=producer)

    response = auth_client(owner).put(
        roles_url(employee), {"role_ids": [str(foreman.id)]}, format="json"
    )

    assert response.status_code == 200
    assert {role["code"] for role in response.data["roles"]} == {FOREMAN}
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ACCOUNT_ROLES_CHANGED,
        target_user=employee,
        actor=owner,
    ).exists()


def test_cannot_change_roles_of_the_producer_account(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    admin = make_administrator()
    foreman = get_system_role(FOREMAN)

    response = auth_client(admin).put(
        roles_url(owner), {"role_ids": [str(foreman.id)]}, format="json"
    )

    assert response.status_code == 400
    assert "role_ids" in response.data["fields"]


def test_cannot_change_roles_of_an_administrator_account(auth_client):
    admin = make_administrator()
    other_admin = make_administrator()
    foreman = get_system_role(FOREMAN)

    response = auth_client(admin).put(
        roles_url(other_admin), {"role_ids": [str(foreman.id)]}, format="json"
    )

    assert response.status_code == 400
    assert "role_ids" in response.data["fields"]


def test_cannot_change_ones_own_roles(auth_client):
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_update"])
    foreman = get_system_role(FOREMAN)

    response = auth_client(delegate).put(
        roles_url(delegate), {"role_ids": [str(foreman.id)]}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "self_modification"


def test_role_ids_must_belong_to_the_actors_scope(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    foreign_role = RoleFactory()

    response = auth_client(owner).put(
        roles_url(employee), {"role_ids": [str(foreign_role.id)]}, format="json"
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_a_delegate_cannot_assign_a_role_beyond_its_own_permissions(auth_client):
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_update"])
    employee = UserFactory(producer=producer)
    stronger_role = RoleFactory(producer=producer, permissions=["accounts.roles_manage"])

    response = auth_client(delegate).put(
        roles_url(employee), {"role_ids": [str(stronger_role.id)]}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_roles_cannot_be_empty(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    response = auth_client(owner).put(roles_url(employee), {"role_ids": []}, format="json")

    assert response.status_code == 400


# --- Estado (PATCH /api/users/{id}/status) -------------------------------------------------------


def test_status_requires_users_change_status_permission(auth_client):
    producer = ProducerFactory()
    viewer = make_delegate(producer, ["accounts.users_update"])
    employee = UserFactory(producer=producer)

    response = auth_client(viewer).patch(
        status_url(employee), {"status": "inactive"}, format="json"
    )

    assert response.status_code == 403


def test_deactivate_and_reactivate_an_employee(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    deactivated = auth_client(owner).patch(
        status_url(employee), {"status": "inactive"}, format="json"
    )
    assert deactivated.status_code == 200
    assert deactivated.data["status"] == "inactive"
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ACCOUNT_DEACTIVATED, target_user=employee
    ).exists()

    reactivated = auth_client(owner).patch(
        status_url(employee), {"status": "active"}, format="json"
    )
    assert reactivated.status_code == 200
    assert reactivated.data["status"] == "active"
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ACCOUNT_REACTIVATED, target_user=employee
    ).exists()


def test_setting_the_same_status_is_idempotent(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    response = auth_client(owner).patch(status_url(employee), {"status": "active"}, format="json")

    assert response.status_code == 200
    assert not AccountManagementEvent.objects.filter(target_user=employee).exists()


def test_deactivating_revokes_the_targets_session(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    employee_client = open_session(csrf_client(), employee)

    response = auth_client(owner).patch(
        status_url(employee), {"status": "inactive"}, format="json"
    )

    assert response.status_code == 200
    assert employee_client.get("/api/auth/me").status_code == 401
    assert employee_client.post("/api/auth/refresh").status_code == 401


def test_cannot_change_ones_own_status(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).patch(status_url(owner), {"status": "inactive"}, format="json")

    assert response.status_code == 403
    assert response.data["code"] == "self_modification"


def test_deactivating_the_only_administrator_is_rejected(auth_client):
    # Nadie puede desactivarse a sí mismo, así que a quien quede como único activo no puede
    # desactivarlo otro administrador (ya estaría inactivo) ni él mismo: se usa un superusuario,
    # que si puede alcanzar cualquier cuenta pero sigue sujeto a esta regla.
    superuser = UserFactory(is_superuser=True)
    remaining = make_administrator()
    doomed = make_administrator()

    first = auth_client(superuser).patch(status_url(doomed), {"status": "inactive"}, format="json")
    assert first.status_code == 200

    second = auth_client(superuser).patch(
        status_url(remaining), {"status": "inactive"}, format="json"
    )
    assert second.status_code == 409
    assert second.data["code"] == "last_administrator"


@pytest.mark.django_db(transaction=True)
def test_concurrent_cross_deactivation_of_two_administrators_leaves_one_active(system_roles):
    first = make_administrator()
    second = make_administrator()
    clients = [open_session(csrf_client(), first), open_session(csrf_client(), second)]
    targets = [second, first]
    barrier = Barrier(2)

    def attempt(pair):
        client, target = pair
        try:
            barrier.wait()
            return client.patch(status_url(target), {"status": "inactive"}, format="json")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(attempt, zip(clients, targets)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.data["code"] == "last_administrator"
    assert User.objects.filter(pk__in=[first.pk, second.pk], is_active=True).count() == 1


# --- Reenvío de activación (POST /api/users/{id}/resend-activation) ------------------------------


def test_resend_activation_requires_users_update_permission(auth_client):
    producer = ProducerFactory()
    viewer = make_delegate(producer, ["accounts.users_view"])
    pending = grant_role(make_pending_user(producer=producer), get_system_role(FOREMAN))

    response = auth_client(viewer).post(resend_url(pending))

    assert response.status_code == 403


def test_resend_activation_for_a_pending_account(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    pending = grant_role(make_pending_user(producer=producer), get_system_role(FOREMAN))

    response = auth_client(owner).post(resend_url(pending))

    assert response.status_code == 200
    assert response.data["activation_email_sent"] is True
    assert len(mail.outbox) == 1


def test_resend_activation_for_an_already_activated_account_is_rejected(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)

    response = auth_client(owner).post(resend_url(employee))

    assert response.status_code == 409
    assert response.data["code"] == "not_activation_pending"


def test_resend_activation_has_its_own_quota_per_actor(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    limit = ActivationResendThrottle().num_requests

    for _ in range(limit):
        pending = grant_role(make_pending_user(producer=producer), get_system_role(FOREMAN))
        auth_client(owner).post(resend_url(pending))

    one_more = grant_role(make_pending_user(producer=producer), get_system_role(FOREMAN))
    response = auth_client(owner).post(resend_url(one_more))

    assert response.status_code == 429
