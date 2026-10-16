from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.common import alerts
from apps.common.alerts import NotificationDraft
from apps.notifications.models import Notification
from apps.notifications.services.create import create_notifications
from apps.notifications.tests.factories import NotificationFactory

pytestmark = pytest.mark.django_db


def draft_for(activity, recipient, *, kind="activity_upcoming", key=None):
    return NotificationDraft(
        recipient_id=recipient.pk,
        kind=kind,
        condition_key=key or f"{activity.pk}:{activity.scheduled_date}:2",
        thread_key=f"activity:{activity.pk}",
        activity_id=activity.pk,
        condition_date=activity.scheduled_date,
    )


def test_it_creates_the_notifications_and_says_how_many():
    activity = AgriculturalActivityFactory()

    created = create_notifications([draft_for(activity, activity.assignee)])

    assert created == 1
    notification = Notification.objects.get()
    assert notification.recipient == activity.assignee
    assert notification.activity == activity
    assert notification.condition_date == activity.scheduled_date
    assert notification.thread_key == f"activity:{activity.pk}"


def test_the_same_drafts_twice_do_not_duplicate():
    activity = AgriculturalActivityFactory()
    drafts = [draft_for(activity, activity.assignee)]

    create_notifications(drafts)
    created = create_notifications(drafts)

    assert created == 0
    assert Notification.objects.count() == 1


def test_nothing_to_create_is_fine():
    assert create_notifications([]) == 0


def test_a_new_reminder_hides_the_previous_one_of_the_same_activity():
    activity = AgriculturalActivityFactory()
    yesterday = create_notifications([draft_for(activity, activity.assignee, key="day-2")])

    create_notifications([draft_for(activity, activity.assignee, key="day-1")])

    assert yesterday == 1
    old = Notification.objects.get(condition_key="day-2")
    new = Notification.objects.get(condition_key="day-1")
    assert old.dismissed_at is not None
    assert old.read_at is not None
    assert new.dismissed_at is None
    assert new.read_at is None


def test_the_overdue_one_replaces_the_delayed_one():
    activity = AgriculturalActivityFactory()
    create_notifications([draft_for(activity, activity.assignee, kind="activity_delayed")])

    create_notifications([draft_for(activity, activity.assignee, kind="activity_overdue")])

    delayed = Notification.objects.get(kind="activity_delayed")
    assert delayed.dismissed_at is not None


def test_the_replacement_is_per_person():
    activity = AgriculturalActivityFactory()
    foreman = UserFactory(producer=activity.plot.farm.producer)
    create_notifications([draft_for(activity, foreman, kind="activity_delayed", key="d1")])

    create_notifications(
        [draft_for(activity, activity.assignee, kind="activity_delayed", key="d2")]
    )

    assert Notification.objects.get(recipient=foreman).dismissed_at is None


def test_another_activity_is_another_thread():
    first = AgriculturalActivityFactory()
    second = AgriculturalActivityFactory(plot=first.plot, assignee=first.assignee)
    create_notifications([draft_for(first, first.assignee)])

    create_notifications([draft_for(second, first.assignee)])

    assert Notification.objects.filter(dismissed_at__isnull=True).count() == 2


def test_a_repeated_draft_does_not_hide_anything():
    activity = AgriculturalActivityFactory()
    drafts = [draft_for(activity, activity.assignee)]
    create_notifications(drafts)

    create_notifications(drafts)

    assert Notification.objects.get().dismissed_at is None


def test_a_dismissed_notification_does_not_come_back():
    notification = NotificationFactory(dismissed_at=timezone.now())
    again = NotificationDraft(
        recipient_id=notification.recipient_id,
        kind=notification.kind,
        condition_key=notification.condition_key,
        thread_key=notification.thread_key,
        activity_id=notification.activity_id,
    )

    assert create_notifications([again]) == 0
    notification.refresh_from_db()
    assert notification.dismissed_at is not None


def test_hiding_keeps_when_it_was_read():
    activity = AgriculturalActivityFactory()
    read_at = timezone.now() - timedelta(hours=3)
    NotificationFactory(
        activity=activity, condition_key="day-2", read_at=read_at, kind="activity_upcoming"
    )

    create_notifications([draft_for(activity, activity.assignee, key="day-1")])

    assert Notification.objects.get(condition_key="day-2").read_at == read_at


def test_notifications_registers_itself_as_the_sink():
    assert alerts._sink is create_notifications
