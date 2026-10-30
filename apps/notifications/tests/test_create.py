from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.common.contracts import alerts
from apps.common.contracts.alerts import NotificationDraft
from apps.drying.tests.factories import DryingLogEntryFactory
from apps.fermentation.tests.factories import FermentationTurnFactory
from apps.lots.tests.factories import LotFactory
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


def statements(captured, verb):
    return [q["sql"] for q in captured if q["sql"].startswith(verb)]


def test_conditions_already_notified_cost_no_write():
    activities = [AgriculturalActivityFactory() for _ in range(3)]
    drafts = [draft_for(a, a.assignee) for a in activities]
    create_notifications(drafts)

    with CaptureQueriesContext(connection) as captured:
        created = create_notifications(drafts)

    assert created == 0
    assert statements(captured, "INSERT") == []
    assert statements(captured, "UPDATE") == []


def test_a_new_one_among_existing_ones_is_the_only_one_written():
    old = AgriculturalActivityFactory()
    create_notifications([draft_for(old, old.assignee)])
    fresh = AgriculturalActivityFactory()

    created = create_notifications(
        [draft_for(old, old.assignee), draft_for(fresh, fresh.assignee)]
    )

    assert created == 1
    assert Notification.objects.filter(activity=fresh).count() == 1
    assert Notification.objects.count() == 2


def test_hiding_the_previous_ones_goes_in_bounded_statements(monkeypatch):
    # Con un trozo de 2, cinco hilos se ocultan en tres sentencias y no en una gigante.
    monkeypatch.setattr("apps.notifications.services.create.CHUNK_SIZE", 2, raising=False)
    activities = [AgriculturalActivityFactory() for _ in range(5)]
    create_notifications([draft_for(a, a.assignee, key="yesterday") for a in activities])

    with CaptureQueriesContext(connection) as captured:
        create_notifications([draft_for(a, a.assignee, key="today") for a in activities])

    assert (
        Notification.objects.filter(condition_key="yesterday", dismissed_at__isnull=False).count()
        == 5
    )
    assert (
        Notification.objects.filter(condition_key="today", dismissed_at__isnull=True).count() == 5
    )
    assert len(statements(captured, "UPDATE")) == 3


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


# Los avisos de un lote.


def lot_draft(lot, recipient, kind, key, **fields):
    return NotificationDraft(
        recipient_id=recipient.pk,
        kind=kind,
        condition_key=key,
        thread_key=f"lot:{lot.pk}",
        lot_id=lot.pk,
        **fields,
    )


def test_a_lot_draft_keeps_its_lot_and_its_condition_time():
    lot = LotFactory()
    recipient = UserFactory()
    due_at = timezone.now()

    create_notifications(
        [lot_draft(lot, recipient, "fermentation_turn_due", "t:2", condition_at=due_at)]
    )

    notification = Notification.objects.get()
    assert notification.lot == lot
    assert notification.activity is None
    assert notification.condition_at == due_at


def test_a_lot_moment_draft_keeps_its_record():
    turn = FermentationTurnFactory()
    entry = DryingLogEntryFactory()
    recipient = UserFactory()

    create_notifications(
        [
            lot_draft(
                turn.process.lot,
                recipient,
                "fermentation_ph_low",
                f"{turn.pk}:fermentation_ph_low",
                fermentation_turn_id=turn.pk,
            ),
            lot_draft(
                entry.process.lot,
                recipient,
                "drying_overdried",
                f"{entry.pk}:drying_overdried",
                drying_log_id=entry.pk,
                severity="critical",
            ),
        ]
    )

    assert Notification.objects.get(kind="fermentation_ph_low").fermentation_turn == turn
    overdried = Notification.objects.get(kind="drying_overdried")
    assert overdried.drying_log == entry
    assert overdried.severity == "critical"


def test_the_pending_turn_replaces_the_reminder_of_the_same_lot():
    lot = LotFactory()
    responsible = UserFactory()
    create_notifications(
        [lot_draft(lot, responsible, "fermentation_first_turn_due", f"{lot.pk}:first_turn")]
    )

    create_notifications(
        [lot_draft(lot, responsible, "fermentation_turn_due", f"{lot.pk}:turn:1")]
    )

    reminder = Notification.objects.get(kind="fermentation_first_turn_due")
    assert reminder.dismissed_at is not None
    assert Notification.objects.get(kind="fermentation_turn_due").dismissed_at is None


def hours_ago(hours):
    return timezone.now() - timedelta(hours=hours)


def lot_moment_draft(lot, recipient, key, condition_at):
    return lot_draft(lot, recipient, "fermentation_turn_due", key, condition_at=condition_at)


def test_a_newer_measurement_replaces_the_older_one_of_its_thread():
    lot = LotFactory()
    recipient = UserFactory()
    create_notifications([lot_moment_draft(lot, recipient, "old", hours_ago(30))])

    create_notifications([lot_moment_draft(lot, recipient, "new", hours_ago(6))])

    assert Notification.objects.get(condition_key="old").dismissed_at is not None
    assert Notification.objects.get(condition_key="new").dismissed_at is None


def test_an_older_measurement_arriving_late_does_not_replace_the_newer_one():
    lot = LotFactory()
    recipient = UserFactory()
    create_notifications([lot_moment_draft(lot, recipient, "new", hours_ago(6))])

    created = create_notifications([lot_moment_draft(lot, recipient, "late", hours_ago(30))])

    assert created == 1
    assert Notification.objects.get(condition_key="new").dismissed_at is None
    late = Notification.objects.get(condition_key="late")
    assert late.dismissed_at is not None
    assert late.read_at is not None


def test_a_late_one_is_not_created_again_by_the_next_evaluation():
    lot = LotFactory()
    recipient = UserFactory()
    create_notifications([lot_moment_draft(lot, recipient, "new", hours_ago(6))])
    late = [lot_moment_draft(lot, recipient, "late", hours_ago(30))]
    create_notifications(late)

    assert create_notifications(late) == 0


def test_two_new_ones_of_a_thread_in_one_batch_both_stay():
    lot = LotFactory()
    recipient = UserFactory()

    create_notifications(
        [
            lot_moment_draft(lot, recipient, "first", hours_ago(30)),
            lot_moment_draft(lot, recipient, "second", hours_ago(6)),
        ]
    )

    assert Notification.objects.filter(dismissed_at__isnull=True).count() == 2


def test_the_same_moment_replaces_the_previous_one():
    lot = LotFactory()
    recipient = UserFactory()
    moment = hours_ago(6)
    create_notifications([lot_moment_draft(lot, recipient, "first", moment)])

    create_notifications([lot_moment_draft(lot, recipient, "second", moment)])

    assert Notification.objects.get(condition_key="first").dismissed_at is not None
    assert Notification.objects.get(condition_key="second").dismissed_at is None


def test_the_order_is_per_person():
    lot = LotFactory()
    first, second = UserFactory(), UserFactory()
    create_notifications([lot_moment_draft(lot, first, "new", hours_ago(6))])

    create_notifications([lot_moment_draft(lot, second, "late", hours_ago(30))])

    assert Notification.objects.get(recipient=second).dismissed_at is None


def test_hiding_the_late_ones_goes_in_bounded_statements(monkeypatch):
    monkeypatch.setattr("apps.notifications.services.create.CHUNK_SIZE", 2, raising=False)
    recipient = UserFactory()
    lots = [LotFactory() for _ in range(5)]
    create_notifications(
        [lot_moment_draft(lot, recipient, f"new:{lot.pk}", hours_ago(6)) for lot in lots]
    )

    with CaptureQueriesContext(connection) as captured:
        create_notifications(
            [lot_moment_draft(lot, recipient, f"late:{lot.pk}", hours_ago(30)) for lot in lots]
        )

    assert (
        Notification.objects.filter(
            condition_key__startswith="late:", dismissed_at__isnull=False
        ).count()
        == 5
    )
    assert len(statements(captured, "UPDATE")) == 3


def test_notifications_registers_itself_as_the_sink():
    assert alerts._sink.create is create_notifications
