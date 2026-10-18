import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import UserFactory
from apps.notifications.choices import NotificationKind, NotificationSeverity
from apps.notifications.models import Notification, PushSubscription
from apps.notifications.tests.factories import NotificationFactory, PushSubscriptionFactory

pytestmark = pytest.mark.django_db


def test_a_new_notification_is_normal_unread_and_not_pushed():
    notification = NotificationFactory()

    assert notification.severity == NotificationSeverity.NORMAL
    assert notification.read_at is None
    assert notification.dismissed_at is None
    assert notification.pushed_at is None


def test_the_same_condition_is_notified_once_per_person():
    first = NotificationFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        NotificationFactory(
            activity=first.activity,
            recipient=first.recipient,
            condition_key=first.condition_key,
        )


def test_the_same_condition_reaches_each_person_separately():
    first = NotificationFactory()
    other = UserFactory(producer=first.activity.plot.farm.producer)

    NotificationFactory(
        activity=first.activity, recipient=other, condition_key=first.condition_key
    )

    assert Notification.objects.filter(condition_key=first.condition_key).count() == 2


def test_another_kind_with_the_same_key_is_another_condition():
    first = NotificationFactory()

    NotificationFactory(
        activity=first.activity,
        recipient=first.recipient,
        condition_key=first.condition_key,
        kind=NotificationKind.ACTIVITY_DELAYED,
    )

    assert Notification.objects.filter(recipient=first.recipient).count() == 2


@pytest.mark.parametrize(
    "kind",
    [
        NotificationKind.ACTIVITY_UPCOMING,
        NotificationKind.ACTIVITY_DELAYED,
        NotificationKind.ACTIVITY_OVERDUE,
    ],
)
def test_an_activity_notification_needs_its_activity(kind):
    with pytest.raises(IntegrityError), transaction.atomic():
        Notification.objects.create(
            recipient=UserFactory(),
            kind=kind,
            condition_key="x",
            thread_key="activity:x",
        )


def test_deleting_the_activity_deletes_its_notifications():
    notification = NotificationFactory()

    notification.activity.delete()

    assert not Notification.objects.filter(pk=notification.pk).exists()


def test_deleting_the_recipient_deletes_their_notifications():
    # Alguien que no es el responsable: la cuenta responsable de una labor no se elimina.
    notification = NotificationFactory(recipient=UserFactory())

    notification.recipient.delete()

    assert not Notification.objects.filter(pk=notification.pk).exists()


def test_an_endpoint_belongs_to_a_single_subscription():
    first = PushSubscriptionFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        PushSubscriptionFactory(endpoint=first.endpoint)


def test_deleting_the_account_deletes_its_subscriptions():
    subscription = PushSubscriptionFactory()

    subscription.user.delete()

    assert not PushSubscription.objects.filter(pk=subscription.pk).exists()


def test_a_pending_control_needs_its_detection():
    activity = NotificationFactory().activity

    with pytest.raises(IntegrityError), transaction.atomic():
        Notification.objects.create(
            recipient=activity.assignee,
            kind=NotificationKind.DETECTION_CONTROL_PENDING,
            activity=activity,
            condition_key="d:0",
            thread_key="detection:d",
        )
