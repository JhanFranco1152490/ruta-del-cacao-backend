import uuid
from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.tests.factories import AgriculturalActivityFactory

pytestmark = pytest.mark.django_db


def test_a_new_activity_starts_scheduled_in_version_one():
    activity = AgriculturalActivityFactory()

    assert activity.status == ActivityStatus.SCHEDULED
    assert activity.version == 1
    assert activity.done_date is None


def test_other_needs_its_description():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityFactory(activity_type=ActivityType.OTHER, other_description=None)


def test_a_blank_description_does_not_count():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityFactory(activity_type=ActivityType.OTHER, other_description="")


def test_only_other_carries_a_description():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityFactory(
            activity_type=ActivityType.PRUNING, other_description="Resiembra"
        )


def test_other_with_its_description_is_accepted():
    activity = AgriculturalActivityFactory(
        activity_type=ActivityType.OTHER, other_description="Resiembra"
    )

    assert activity.other_description == "Resiembra"


def test_done_needs_its_date_and_when_it_was_recorded():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityFactory(status=ActivityStatus.DONE, done_date=None)


def test_a_scheduled_activity_has_no_completion_data():
    with pytest.raises(IntegrityError), transaction.atomic():
        AgriculturalActivityFactory(done_date=date(2026, 10, 1))


def test_a_done_activity_keeps_its_completion_data():
    activity = AgriculturalActivityFactory(
        status=ActivityStatus.DONE, done_date=date(2026, 10, 1), completed_at=timezone.now()
    )

    assert activity.status == ActivityStatus.DONE


def test_an_assigned_account_cannot_be_deleted():
    activity = AgriculturalActivityFactory()

    with pytest.raises(ProtectedError):
        activity.assignee.delete()


def test_deleting_who_recorded_the_completion_keeps_the_activity():
    recorder = UserFactory()
    activity = AgriculturalActivityFactory(
        status=ActivityStatus.DONE,
        done_date=date(2026, 10, 1),
        completed_at=timezone.now(),
        completed_by=recorder,
    )

    recorder.delete()

    activity.refresh_from_db()
    assert activity.completed_by is None


def test_a_plot_with_activities_is_protected_at_the_database():
    activity = AgriculturalActivityFactory()

    with pytest.raises(ProtectedError):
        activity.plot.delete()


def test_the_history_survives_the_activity():
    activity = AgriculturalActivityFactory()
    event = AgriculturalActivityAuditEvent.record(
        action=AgriculturalActivityAuditEvent.Action.CREATED,
        changed_fields=["activity_type"],
        activity=activity,
        activity_ref=activity.pk,
        plot_ref=activity.plot_id,
        actor=activity.assignee,
        version=1,
        changes={"activity_type": {"before": None, "after": "pruning"}},
    )
    activity_id = activity.pk

    activity.delete()

    event.refresh_from_db()
    assert event.activity is None
    assert event.activity_ref == activity_id
    assert event.changes == {"activity_type": {"before": None, "after": "pruning"}}


def test_the_client_can_choose_the_id():
    chosen = uuid.uuid4()

    activity = AgriculturalActivityFactory(id=chosen)

    assert AgriculturalActivity.objects.get(pk=chosen) == activity
