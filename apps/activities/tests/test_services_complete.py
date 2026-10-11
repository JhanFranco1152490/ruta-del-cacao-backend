import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.exceptions import (
    ActivityAlreadyDone,
    ActivityNotFound,
    InvalidActivity,
    MonitoringRequiresResult,
)
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.services.complete import complete_activity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

COMPLETED = AgriculturalActivityAuditEvent.Action.COMPLETED


def today():
    return today_in_bogota()


def scheduled_in(days, **kwargs):
    activity = AgriculturalActivityFactory(scheduled_date=today() + timedelta(days=days), **kwargs)
    # Programada hace diez días, para poder registrar una realización de días pasados.
    AgriculturalActivity.objects.filter(pk=activity.pk).update(
        created_at=timezone.now() - timedelta(days=10)
    )
    activity.refresh_from_db()
    return activity


def member_of(activity):
    return UserFactory(producer=activity.plot.farm.producer)


def completion(done_date=None, **overrides):
    values = {"done_date": done_date or today(), "inputs": [], "captured_at": None}
    values.update(overrides)
    return values


def completed_events(activity):
    return AgriculturalActivityAuditEvent.objects.filter(activity=activity, action=COMPLETED)


@pytest.mark.parametrize("days", [2, -1, -4], ids=["scheduled", "delayed", "overdue"])
def test_scheduled_delayed_and_overdue_activities_are_completed(days):
    activity = scheduled_in(days)
    actor = member_of(activity)

    completed, changed = complete_activity(actor, activity.pk, completion())

    assert changed is True
    stored = AgriculturalActivity.objects.get(pk=activity.pk)
    assert stored.status == ActivityStatus.DONE
    assert stored.done_date == today()
    assert stored.completed_by == actor
    assert stored.completed_at is not None
    assert stored.version == completed.version == 2


def test_who_records_it_may_not_be_the_assignee():
    activity = scheduled_in(1)
    recorder = member_of(activity)

    complete_activity(recorder, activity.pk, completion())

    stored = AgriculturalActivity.objects.get(pk=activity.pk)
    assert stored.completed_by == recorder
    assert stored.assignee == activity.assignee


def test_it_leaves_the_completed_event_with_the_date():
    activity = scheduled_in(1)
    actor = member_of(activity)

    complete_activity(actor, activity.pk, completion())

    [event] = completed_events(activity)
    assert event.actor == actor
    assert event.version == 2
    assert event.changes["status"] == {"before": "scheduled", "after": "done"}
    assert event.changes["done_date"] == {"before": None, "after": today().isoformat()}


def test_it_keeps_the_time_the_phone_captured_it():
    activity = scheduled_in(1)
    captured = datetime(2026, 10, 9, 21, 42, tzinfo=dt_timezone.utc)

    complete_activity(member_of(activity), activity.pk, completion(captured_at=captured))

    assert AgriculturalActivity.objects.get(pk=activity.pk).captured_at == captured


def test_a_future_date_is_rejected():
    activity = scheduled_in(1)

    with pytest.raises(InvalidActivity) as error:
        complete_activity(
            member_of(activity), activity.pk, completion(today() + timedelta(days=1))
        )

    assert "done_date" in error.value.fields
    assert AgriculturalActivity.objects.get(pk=activity.pk).status == ActivityStatus.SCHEDULED


def test_a_date_before_it_was_scheduled_is_rejected():
    activity = scheduled_in(1)

    with pytest.raises(InvalidActivity) as error:
        complete_activity(
            member_of(activity), activity.pk, completion(today() - timedelta(days=11))
        )

    assert "done_date" in error.value.fields


def test_a_date_before_the_scheduled_one_but_after_planning_is_accepted():
    # La labor se adelantó: se programó para dentro de dos días y se hizo anteayer.
    activity = scheduled_in(2)

    complete_activity(member_of(activity), activity.pk, completion(today() - timedelta(days=2)))

    assert AgriculturalActivity.objects.get(pk=activity.pk).done_date == today() - timedelta(
        days=2
    )


def test_an_unknown_input_leaves_the_activity_scheduled():
    activity = scheduled_in(1)

    with pytest.raises(InvalidActivity) as error:
        complete_activity(
            member_of(activity),
            activity.pk,
            completion(inputs=[{"input_id": uuid.uuid4(), "quantity": "2"}]),
        )

    assert "inputs" in error.value.fields
    assert AgriculturalActivity.objects.get(pk=activity.pk).status == ActivityStatus.SCHEDULED


def test_a_monitoring_is_not_completed_here():
    monitoring = scheduled_in(1, activity_type=ActivityType.PHYTOSANITARY_MONITORING)

    with pytest.raises(MonitoringRequiresResult):
        complete_activity(member_of(monitoring), monitoring.pk, completion())


def test_an_inactive_plot_and_farm_do_not_block_it():
    activity = scheduled_in(-1)
    activity.plot.is_active = False
    activity.plot.save(update_fields=["is_active"])
    activity.plot.farm.is_active = False
    activity.plot.farm.save(update_fields=["is_active"])

    _, changed = complete_activity(member_of(activity), activity.pk, completion())

    assert changed is True


def test_a_resend_of_the_same_completion_changes_nothing():
    activity = scheduled_in(1)
    actor = member_of(activity)
    complete_activity(actor, activity.pk, completion())

    again, changed = complete_activity(actor, activity.pk, completion())

    assert changed is False
    assert again.version == 2
    assert completed_events(activity).count() == 1


def test_a_completion_with_other_data_on_a_done_activity_is_rejected():
    activity = scheduled_in(1)
    actor = member_of(activity)
    complete_activity(actor, activity.pk, completion())

    with pytest.raises(ActivityAlreadyDone):
        complete_activity(actor, activity.pk, completion(today() - timedelta(days=1)))

    assert AgriculturalActivity.objects.get(pk=activity.pk).done_date == today()


def test_an_activity_of_another_producer_is_not_found():
    activity = scheduled_in(1)
    stranger = UserFactory(producer=PlotFactory().farm.producer)

    with pytest.raises(ActivityNotFound):
        complete_activity(stranger, activity.pk, completion())
