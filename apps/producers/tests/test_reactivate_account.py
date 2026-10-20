"""Reactivar un productor reactiva también su cuenta Productor, si estaba desactivada."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import AccountManagementEvent
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.producers.models import Producer

from .factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def status_url(producer) -> str:
    return f"/api/producers/{producer.id}/status"


def inactive_producer():
    return ProducerFactory(status=Producer.Status.INACTIVE)


def deactivated(account):
    account.is_active = False
    account.save(update_fields=["is_active"])
    return account


def test_reactivating_a_producer_reactivates_its_account(admin_client):
    producer = inactive_producer()
    account = deactivated(make_producer_owner(producer))

    response = admin_client.patch(
        status_url(producer), {"status": "active", "expected_version": 1}, format="json"
    )

    assert response.status_code == 200
    account.refresh_from_db()
    assert account.is_active
    event = AccountManagementEvent.objects.get(
        event_type=AccountManagementEvent.EventType.ACCOUNT_REACTIVATED, target_user=account
    )
    assert event.actor is not None


def test_it_leaves_the_accounts_of_its_employees_as_they_were(admin_client):
    producer = inactive_producer()
    employee = UserFactory(producer=producer, is_active=False)

    admin_client.patch(
        status_url(producer), {"status": "active", "expected_version": 1}, format="json"
    )

    employee.refresh_from_db()
    assert not employee.is_active


def test_a_producer_without_an_account_is_reactivated_alone(admin_client):
    producer = inactive_producer()

    response = admin_client.patch(
        status_url(producer), {"status": "active", "expected_version": 1}, format="json"
    )

    assert response.status_code == 200
    assert response.data["status"] == "active"


def test_deactivating_a_producer_leaves_its_account_alone(admin_client):
    producer = ProducerFactory()
    account = make_producer_owner(producer)

    admin_client.patch(
        status_url(producer), {"status": "inactive", "expected_version": 1}, format="json"
    )

    account.refresh_from_db()
    assert account.is_active
    assert not AccountManagementEvent.objects.filter(target_user=account).exists()


def test_the_django_admin_reactivates_the_account_too():
    producer = inactive_producer()
    account = deactivated(make_producer_owner(producer))
    staff = UserFactory(is_staff=True, permissions=["producers.view", "producers.change_status"])
    client = Client()
    client.force_login(staff)

    client.post(
        reverse("admin:producers_producer_changelist"),
        {"action": "activate", "_selected_action": [str(producer.pk)]},
        follow=True,
    )

    account.refresh_from_db()
    assert account.is_active
    assert (
        AccountManagementEvent.objects.get(target_user=account, actor=staff).event_type
        == AccountManagementEvent.EventType.ACCOUNT_REACTIVATED
    )
