from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus
from apps.activities.exceptions import (
    ActivityAlreadyDone,
    ActivityNotFound,
    ActivityOverdue,
    StaleActivityVersion,
)
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.services.delete import delete_activity, remove_activity
from apps.activities.services.update import update_activity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

DELETED = AgriculturalActivityAuditEvent.Action.DELETED


def scheduled_in(days):
    return AgriculturalActivityFactory(scheduled_date=today_in_bogota() + timedelta(days=days))


def member_of(activity):
    return UserFactory(producer=activity.plot.farm.producer)


def exists(activity) -> bool:
    return AgriculturalActivity.objects.filter(pk=activity.pk).exists()


@pytest.mark.parametrize("days", [3, -1], ids=["scheduled", "delayed"])
def test_a_scheduled_or_delayed_activity_is_deleted_and_its_history_survives(days):
    activity = scheduled_in(days)
    actor = member_of(activity)
    activity_id, plot_id = activity.pk, activity.plot_id

    delete_activity(actor, activity_id, 1)

    assert not AgriculturalActivity.objects.filter(pk=activity_id).exists()
    event = AgriculturalActivityAuditEvent.objects.get(activity_ref=activity_id, action=DELETED)
    assert event.activity is None
    assert event.plot_ref == plot_id
    assert event.actor == actor
    assert event.changes["activity_type"] == {"before": "pruning", "after": None}


def test_a_done_activity_is_not_deleted():
    done = AgriculturalActivityFactory(
        status=ActivityStatus.DONE, done_date=today_in_bogota(), completed_at=timezone.now()
    )

    with pytest.raises(ActivityAlreadyDone):
        delete_activity(member_of(done), done.pk, 1)

    assert exists(done)


def test_an_overdue_activity_is_kept_as_evidence():
    overdue = scheduled_in(-3)

    with pytest.raises(ActivityOverdue):
        delete_activity(member_of(overdue), overdue.pk, 1)

    assert exists(overdue)


def test_an_old_version_is_not_deleted():
    activity = scheduled_in(3)
    actor = member_of(activity)
    update_activity(actor, activity.pk, 1, {"scheduled_date": today_in_bogota()})

    with pytest.raises(StaleActivityVersion):
        delete_activity(actor, activity.pk, 1)

    assert exists(activity)


def test_an_activity_of_another_producer_is_not_found():
    activity = scheduled_in(3)
    stranger = UserFactory(producer=PlotFactory().farm.producer)

    with pytest.raises(ActivityNotFound):
        delete_activity(stranger, activity.pk, 1)

    assert exists(activity)


def test_removing_for_a_cascade_does_not_check_the_state():
    # Lo usa quien ya decidió borrar, como la eliminación de una parcela creada por error: lo que
    # no se llegó a hacer, vencido o no, se va con ella.
    overdue = scheduled_in(-5)
    activity_id = overdue.pk

    remove_activity(overdue, member_of(overdue))

    assert not AgriculturalActivity.objects.filter(pk=activity_id).exists()
    assert AgriculturalActivityAuditEvent.objects.filter(
        activity_ref=activity_id, action=DELETED
    ).exists()
