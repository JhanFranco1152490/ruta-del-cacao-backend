from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.exceptions import (
    ActivityAlreadyDone,
    ActivityNotFound,
    ActivityOverdue,
    ActivityTypeNotAllowed,
    AssigneeNotAvailable,
    InvalidActivity,
    StaleActivityVersion,
)
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.services.update import update_activity
from apps.activities.state import ActivityState, activity_state, today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

UPDATED = AgriculturalActivityAuditEvent.Action.UPDATED


def days_from_today(days):
    return today_in_bogota() + timedelta(days=days)


@pytest.fixture
def activity():
    return AgriculturalActivityFactory(scheduled_date=days_from_today(5))


@pytest.fixture
def actor(activity):
    return UserFactory(producer=activity.plot.farm.producer)


def colleague(activity, **kwargs):
    return UserFactory(producer=activity.plot.farm.producer, **kwargs)


def events(activity):
    return list(AgriculturalActivityAuditEvent.objects.filter(activity=activity, action=UPDATED))


def test_it_changes_type_date_and_assignee_and_raises_the_version(actor, activity):
    new_assignee = colleague(activity)
    old_assignee_id = activity.assignee_id

    updated = update_activity(
        actor,
        activity.pk,
        1,
        {
            "activity_type": ActivityType.IRRIGATION,
            "scheduled_date": days_from_today(8),
            "assignee_id": new_assignee.pk,
        },
    )

    stored = AgriculturalActivity.objects.get(pk=activity.pk)
    assert updated.version == stored.version == 2
    assert stored.activity_type == ActivityType.IRRIGATION
    assert stored.scheduled_date == days_from_today(8)
    assert stored.assignee == new_assignee
    assert stored.plot_id == activity.plot_id
    [event] = events(activity)
    assert event.actor == actor
    assert event.version == 2
    assert event.changes == {
        "activity_type": {"before": "pruning", "after": "irrigation"},
        "scheduled_date": {
            "before": days_from_today(5).isoformat(),
            "after": days_from_today(8).isoformat(),
        },
        "assignee_id": {"before": str(old_assignee_id), "after": str(new_assignee.pk)},
    }


def test_a_delayed_activity_rescheduled_to_tomorrow_is_scheduled_again(actor):
    delayed = AgriculturalActivityFactory(scheduled_date=days_from_today(-1))
    actor = colleague(delayed)

    updated = update_activity(actor, delayed.pk, 1, {"scheduled_date": days_from_today(1)})

    assert activity_state(updated, today_in_bogota())[0] == ActivityState.SCHEDULED


def test_a_delayed_activity_gets_a_new_assignee_without_moving_its_date():
    delayed = AgriculturalActivityFactory(scheduled_date=days_from_today(-2))
    actor = colleague(delayed)
    new_assignee = colleague(delayed)

    updated = update_activity(actor, delayed.pk, 1, {"assignee_id": new_assignee.pk})

    assert updated.assignee == new_assignee
    assert updated.scheduled_date == days_from_today(-2)


def test_a_new_date_in_the_past_is_rejected(actor, activity):
    with pytest.raises(InvalidActivity) as error:
        update_activity(actor, activity.pk, 1, {"scheduled_date": days_from_today(-1)})

    assert "scheduled_date" in error.value.fields
    assert AgriculturalActivity.objects.get(pk=activity.pk).version == 1


def test_an_inactive_assignee_that_does_not_change_does_not_block_other_edits(actor, activity):
    activity.assignee.is_active = False
    activity.assignee.save(update_fields=["is_active"])

    updated = update_activity(actor, activity.pk, 1, {"activity_type": ActivityType.IRRIGATION})

    assert updated.activity_type == ActivityType.IRRIGATION


def test_a_new_inactive_assignee_is_rejected(actor, activity):
    with pytest.raises(AssigneeNotAvailable):
        update_activity(
            actor, activity.pk, 1, {"assignee_id": colleague(activity, is_active=False).pk}
        )


def test_changing_to_other_needs_the_description(actor, activity):
    with pytest.raises(InvalidActivity) as error:
        update_activity(actor, activity.pk, 1, {"activity_type": ActivityType.OTHER})

    assert "other_description" in error.value.fields


def test_leaving_other_drops_the_description(actor):
    other = AgriculturalActivityFactory(
        activity_type=ActivityType.OTHER,
        other_description="Resiembra",
        scheduled_date=days_from_today(3),
    )

    updated = update_activity(
        colleague(other), other.pk, 1, {"activity_type": ActivityType.PRUNING}
    )

    assert updated.other_description is None


def test_it_cannot_become_a_phytosanitary_control(actor, activity):
    with pytest.raises(ActivityTypeNotAllowed):
        update_activity(
            actor, activity.pk, 1, {"activity_type": ActivityType.PHYTOSANITARY_CONTROL}
        )


def test_a_control_created_elsewhere_can_be_rescheduled():
    control = AgriculturalActivityFactory(
        activity_type=ActivityType.PHYTOSANITARY_CONTROL, scheduled_date=days_from_today(2)
    )

    updated = update_activity(
        colleague(control), control.pk, 1, {"scheduled_date": days_from_today(4)}
    )

    assert updated.scheduled_date == days_from_today(4)


def test_a_done_activity_cannot_be_edited():
    done = AgriculturalActivityFactory(
        status=ActivityStatus.DONE,
        done_date=today_in_bogota(),
        completed_at=timezone.now(),
    )

    with pytest.raises(ActivityAlreadyDone):
        update_activity(colleague(done), done.pk, 1, {"scheduled_date": days_from_today(2)})


def test_an_overdue_activity_cannot_be_edited_even_with_the_right_version():
    overdue = AgriculturalActivityFactory(scheduled_date=days_from_today(-3))

    with pytest.raises(ActivityOverdue):
        update_activity(colleague(overdue), overdue.pk, 1, {"scheduled_date": days_from_today(2)})


def test_an_old_version_is_stale_and_carries_the_current_activity(actor, activity):
    update_activity(actor, activity.pk, 1, {"activity_type": ActivityType.IRRIGATION})

    with pytest.raises(StaleActivityVersion) as error:
        update_activity(actor, activity.pk, 1, {"activity_type": ActivityType.WEED_CONTROL})

    assert error.value.current_activity.version == 2
    stored = AgriculturalActivity.objects.get(pk=activity.pk)
    assert stored.activity_type == ActivityType.IRRIGATION


def test_a_replay_already_applied_answers_without_writing(actor, activity):
    change = {"activity_type": ActivityType.IRRIGATION}
    update_activity(actor, activity.pk, 1, change)

    again = update_activity(actor, activity.pk, 1, change)

    assert again.version == 2
    assert len(events(activity)) == 1


def test_no_real_change_keeps_the_version_and_leaves_no_event(actor, activity):
    same = update_activity(actor, activity.pk, 1, {"activity_type": activity.activity_type})

    assert same.version == 1
    assert events(activity) == []


def test_an_inactive_plot_does_not_block_rescheduling(actor, activity):
    activity.plot.is_active = False
    activity.plot.save(update_fields=["is_active"])

    updated = update_activity(actor, activity.pk, 1, {"scheduled_date": days_from_today(9)})

    assert updated.scheduled_date == days_from_today(9)


def test_an_activity_of_another_producer_is_not_found(activity):
    stranger = UserFactory(producer=PlotFactory().farm.producer)

    with pytest.raises(ActivityNotFound):
        update_activity(stranger, activity.pk, 1, {"activity_type": ActivityType.IRRIGATION})
