import pytest
from rest_framework.test import APIClient

from apps.accounts.authorization import ensure_can_grant
from apps.accounts.exceptions import ExceedsOwnPermissions
from apps.accounts.models import AccountManagementEvent, AssociationAccess
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_delegate, make_producer_owner
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

ACCESS_URL = "/api/association-access"


def test_requires_authentication():
    assert APIClient().get(ACCESS_URL).status_code == 401


def test_requires_association_access_manage_permission(auth_client):
    producer = ProducerFactory()
    delegate = make_delegate(producer, ["accounts.users_view", "accounts.roles_manage"])

    assert auth_client(delegate).get(ACCESS_URL).status_code == 403


def test_a_delegate_can_never_hold_the_permission():
    # No delegable (HU-03): un rol propio no puede llevarlo aunque el productor sí lo tenga.
    owner = make_producer_owner(ProducerFactory())

    with pytest.raises(ExceedsOwnPermissions):
        ensure_can_grant(owner, ["accounts.association_access_manage"])


def test_administrator_cannot_access_it_either(auth_client):
    admin = make_administrator()

    response = auth_client(admin).get(ACCESS_URL)

    assert response.status_code == 403


def test_an_account_without_a_producer_gets_not_found(auth_client):
    superuser = UserFactory(is_superuser=True)

    response = auth_client(superuser).get(ACCESS_URL)

    assert response.status_code == 404


def test_default_is_disabled_without_creating_a_row(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    response = auth_client(owner).get(ACCESS_URL)

    assert response.status_code == 200
    assert response.data == {"enabled": False, "changed_at": None}
    assert not AssociationAccess.objects.filter(producer=producer).exists()


def test_enable_and_disable(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    enabled = auth_client(owner).put(ACCESS_URL, {"enabled": True}, format="json")
    assert enabled.status_code == 200
    assert enabled.data["enabled"] is True
    assert enabled.data["changed_at"] is not None
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ASSOCIATION_ACCESS_ENABLED, actor=owner
    ).exists()

    disabled = auth_client(owner).put(ACCESS_URL, {"enabled": False}, format="json")
    assert disabled.status_code == 200
    assert disabled.data["enabled"] is False
    assert AccountManagementEvent.objects.filter(
        event_type=AccountManagementEvent.EventType.ASSOCIATION_ACCESS_DISABLED, actor=owner
    ).exists()


def test_repeating_the_same_value_is_idempotent(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    first = auth_client(owner).put(ACCESS_URL, {"enabled": True}, format="json")
    assert first.status_code == 200
    first_changed_at = first.data["changed_at"]

    second = auth_client(owner).put(ACCESS_URL, {"enabled": True}, format="json")

    assert second.status_code == 200
    assert second.data["changed_at"] == first_changed_at
    assert (
        AccountManagementEvent.objects.filter(
            event_type=AccountManagementEvent.EventType.ASSOCIATION_ACCESS_ENABLED
        ).count()
        == 1
    )


def test_put_rejects_unknown_field(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    response = auth_client(owner).put(
        ACCESS_URL, {"enabled": True, "producer_id": str(producer.id)}, format="json"
    )

    assert response.status_code == 400
    assert "producer_id" in response.data["fields"]


def test_switch_affects_the_administrators_scope(auth_client):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    employee = UserFactory(producer=producer)
    admin = make_administrator()

    hidden = auth_client(admin).get(f"/api/users/{employee.id}")
    assert hidden.status_code == 404

    auth_client(owner).put(ACCESS_URL, {"enabled": True}, format="json")

    shown = auth_client(admin).get(f"/api/users/{employee.id}")
    assert shown.status_code == 200

    auth_client(owner).put(ACCESS_URL, {"enabled": False}, format="json")

    hidden_again = auth_client(admin).get(f"/api/users/{employee.id}")
    assert hidden_again.status_code == 404
