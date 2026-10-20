"""Reactivar la cuenta Productor reactiva también a su productor, y se ve el estado efectivo."""

import uuid

import pytest
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from apps.accounts.models import AccountManagementEvent
from apps.accounts.system_roles import ADMINISTRATOR, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.accounts.users.services import set_account_status
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def status_url(user) -> str:
    return f"/api/users/{user.id}/status"


def inactive_producer_with_account(*, account_active=False):
    producer = ProducerFactory(status=Producer.Status.INACTIVE)
    account = make_producer_owner(producer)
    if not account_active:
        account.is_active = False
        account.save(update_fields=["is_active"])
    return producer, account


def reactivated_events(account):
    return AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ACCOUNT_REACTIVATED, target_user=account
    )


def test_reactivating_the_producer_account_reactivates_its_producer(auth_client):
    producer, account = inactive_producer_with_account()
    administrator = make_administrator()

    response = auth_client(administrator).patch(
        status_url(account), {"status": "active"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["status"] == "active"
    producer.refresh_from_db()
    account.refresh_from_db()
    assert producer.status == Producer.Status.ACTIVE
    assert producer.version == 2
    assert account.is_active
    assert reactivated_events(account).get().actor == administrator


def test_it_reactivates_the_producer_of_an_account_that_was_still_active(auth_client):
    # La cuenta se veía «Activa» pero sin acceso: reactivarla es reactivar a su productor.
    producer, account = inactive_producer_with_account(account_active=True)

    response = auth_client(make_administrator()).patch(
        status_url(account), {"status": "active"}, format="json"
    )

    assert response.status_code == 200
    producer.refresh_from_db()
    assert producer.status == Producer.Status.ACTIVE
    assert not reactivated_events(account).exists()


def test_it_needs_the_permission_to_change_the_status_of_producers(auth_client):
    producer, account = inactive_producer_with_account()
    administrator = make_administrator()
    get_system_role(ADMINISTRATOR).group.permissions.remove(
        Permission.objects.get(content_type__app_label="producers", codename="change_status")
    )

    response = auth_client(administrator).patch(
        status_url(account), {"status": "active"}, format="json"
    )

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"
    producer.refresh_from_db()
    account.refresh_from_db()
    assert producer.status == Producer.Status.INACTIVE
    assert not account.is_active


def test_reactivating_an_employee_does_not_reactivate_its_producer():
    producer = ProducerFactory(status=Producer.Status.INACTIVE)
    employee = UserFactory(producer=producer, is_active=False)

    set_account_status(UserFactory(is_superuser=True), employee.id, "active", uuid.uuid4())

    employee.refresh_from_db()
    producer.refresh_from_db()
    assert employee.is_active
    assert producer.status == Producer.Status.INACTIVE


def test_deactivating_the_producer_account_leaves_its_producer_active(auth_client):
    producer = ProducerFactory()
    account = make_producer_owner(producer)

    response = auth_client(make_administrator()).patch(
        status_url(account), {"status": "inactive"}, format="json"
    )

    assert response.status_code == 200
    producer.refresh_from_db()
    assert producer.status == Producer.Status.ACTIVE


def test_the_django_admin_reactivates_the_producer_too():
    producer, account = inactive_producer_with_account()
    client = Client()
    client.force_login(UserFactory(is_staff=True, is_superuser=True))

    client.post(
        reverse("admin:accounts_user_change", args=[account.pk]),
        {
            "email": account.email,
            "document_type": account.document_type,
            "identity_document": account.identity_document,
            "first_name": account.first_name,
            "last_name": account.last_name,
            "is_active": "on",
        },
    )

    producer.refresh_from_db()
    account.refresh_from_db()
    assert account.is_active
    assert producer.status == Producer.Status.ACTIVE


def test_the_inactive_filter_includes_the_accounts_of_an_inactive_producer(auth_client):
    _, blocked = inactive_producer_with_account(account_active=True)
    active = make_producer_owner(ProducerFactory())
    client = auth_client(make_administrator())

    inactive_ids = {row["id"] for row in client.get("/api/users?status=inactive").data["results"]}
    active_ids = {row["id"] for row in client.get("/api/users?status=active").data["results"]}

    assert str(blocked.id) in inactive_ids
    assert str(blocked.id) not in active_ids
    assert str(active.id) in active_ids
