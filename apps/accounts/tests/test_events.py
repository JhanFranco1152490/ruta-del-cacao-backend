import uuid

import pytest

from apps.accounts.events import record_account_event
from apps.accounts.models import AccountManagementEvent
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_record_account_event_stores_actor_and_target():
    actor = UserFactory()
    target = UserFactory()
    request_id = uuid.uuid4()

    record_account_event(
        AccountManagementEvent.EventType.ACCOUNT_CREATED,
        request_id,
        actor=actor,
        target_user=target,
    )

    event = AccountManagementEvent.objects.get()
    assert event.event_type == AccountManagementEvent.EventType.ACCOUNT_CREATED
    assert event.actor == actor
    assert event.target_user == target
    assert event.target_role_id is None
    assert event.request_id == request_id


def test_record_account_event_stores_role_target_without_actor():
    role_id = uuid.uuid4()

    record_account_event(
        AccountManagementEvent.EventType.ROLE_DELETED,
        uuid.uuid4(),
        target_role_id=role_id,
    )

    event = AccountManagementEvent.objects.get()
    assert event.actor is None
    assert event.target_user is None
    assert event.target_role_id == role_id
