import uuid
from datetime import timedelta

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.exceptions import (
    ActivityIdConflict,
    ActivityTypeNotAllowed,
    AssigneeNotAvailable,
    FarmInactive,
    InvalidActivity,
    PlotInactive,
    PlotNotFound,
)
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.services import audit
from apps.activities.services.create import create_activity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def plot():
    return PlotFactory()


@pytest.fixture
def actor(plot):
    return UserFactory(producer=plot.farm.producer)


@pytest.fixture
def assignee(plot):
    return UserFactory(producer=plot.farm.producer)


def data(plot, assignee, **overrides) -> dict:
    values = {
        "plot_id": plot.pk,
        "activity_type": ActivityType.FERTILIZATION,
        "other_description": None,
        "scheduled_date": today_in_bogota() + timedelta(days=5),
        "assignee_id": assignee.pk,
    }
    values.update(overrides)
    return values


def test_it_schedules_the_activity_on_the_plot(actor, plot, assignee):
    activity, created = create_activity(actor, data(plot, assignee))

    assert created is True
    stored = AgriculturalActivity.objects.get(pk=activity.pk)
    assert stored.plot == plot
    assert stored.activity_type == ActivityType.FERTILIZATION
    assert stored.assignee == assignee
    assert stored.status == ActivityStatus.SCHEDULED
    assert stored.version == 1


def test_it_leaves_the_created_event_with_the_values_and_the_assignee_by_id(actor, plot, assignee):
    activity, _ = create_activity(actor, data(plot, assignee))

    event = AgriculturalActivityAuditEvent.objects.get(activity=activity)
    assert event.action == AgriculturalActivityAuditEvent.Action.CREATED
    assert event.actor == actor
    assert event.version == 1
    assert event.activity_ref == activity.pk
    assert event.plot_ref == plot.pk
    assert event.changes["activity_type"] == {"before": None, "after": "fertilization"}
    assert event.changes["assignee_id"] == {"before": None, "after": str(assignee.pk)}
    assert "full_name" not in str(event.changes)


def test_the_client_chooses_the_id(actor, plot, assignee):
    chosen = uuid.uuid4()

    activity, _ = create_activity(actor, data(plot, assignee, id=chosen))

    assert activity.pk == chosen


def test_today_is_accepted(actor, plot, assignee):
    activity, _ = create_activity(actor, data(plot, assignee, scheduled_date=today_in_bogota()))

    assert activity.scheduled_date == today_in_bogota()


def test_a_past_date_is_rejected(actor, plot, assignee):
    yesterday = today_in_bogota() - timedelta(days=1)

    with pytest.raises(InvalidActivity) as error:
        create_activity(actor, data(plot, assignee, scheduled_date=yesterday))

    assert "scheduled_date" in error.value.fields
    assert not AgriculturalActivity.objects.exists()


def test_other_needs_what_the_task_is(actor, plot, assignee):
    for description in (None, "", "  ", "R"):
        with pytest.raises(InvalidActivity) as error:
            create_activity(
                actor,
                data(
                    plot,
                    assignee,
                    activity_type=ActivityType.OTHER,
                    other_description=description,
                ),
            )
        assert "other_description" in error.value.fields


def test_other_keeps_its_trimmed_description(actor, plot, assignee):
    activity, _ = create_activity(
        actor,
        data(plot, assignee, activity_type=ActivityType.OTHER, other_description="  Resiembra "),
    )

    assert activity.other_description == "Resiembra"


def test_a_description_with_another_type_is_rejected(actor, plot, assignee):
    with pytest.raises(InvalidActivity) as error:
        create_activity(actor, data(plot, assignee, other_description="Resiembra"))

    assert "other_description" in error.value.fields


def test_a_phytosanitary_control_is_not_scheduled_here(actor, plot, assignee):
    with pytest.raises(ActivityTypeNotAllowed):
        create_activity(
            actor, data(plot, assignee, activity_type=ActivityType.PHYTOSANITARY_CONTROL)
        )


def test_a_plot_of_another_producer_is_not_found(plot, assignee):
    stranger = UserFactory(producer=PlotFactory().farm.producer)

    with pytest.raises(PlotNotFound):
        create_activity(stranger, data(plot, assignee))


def test_a_plot_that_does_not_exist_is_not_found(actor, plot, assignee):
    with pytest.raises(PlotNotFound):
        create_activity(actor, data(plot, assignee, plot_id=uuid.uuid4()))


def test_an_inactive_plot_is_rejected(actor, plot, assignee):
    plot.is_active = False
    plot.save(update_fields=["is_active"])

    with pytest.raises(PlotInactive):
        create_activity(actor, data(plot, assignee))


def test_an_inactive_farm_is_reported_before_its_plot(actor, plot, assignee):
    plot.is_active = False
    plot.save(update_fields=["is_active"])
    plot.farm.is_active = False
    plot.farm.save(update_fields=["is_active"])

    with pytest.raises(FarmInactive):
        create_activity(actor, data(plot, assignee))


@pytest.mark.parametrize("who", ["inactive", "other-producer", "missing", "superuser"])
def test_the_assignee_must_be_an_active_account_of_the_plot_producer(actor, plot, who):
    if who == "inactive":
        assignee_id = UserFactory(producer=plot.farm.producer, is_active=False).pk
    elif who == "other-producer":
        assignee_id = UserFactory(producer=PlotFactory().farm.producer).pk
    elif who == "missing":
        assignee_id = uuid.uuid4()
    else:
        assignee_id = UserFactory(is_superuser=True).pk

    with pytest.raises(AssigneeNotAvailable):
        create_activity(actor, {**data(plot, actor), "assignee_id": assignee_id})


def test_a_resend_with_the_same_content_returns_the_activity(actor, plot, assignee):
    values = data(plot, assignee, id=uuid.uuid4())
    first, _ = create_activity(actor, values)

    again, created = create_activity(actor, values)

    assert created is False
    assert again.pk == first.pk
    assert AgriculturalActivity.objects.count() == 1
    assert AgriculturalActivityAuditEvent.objects.count() == 1


def test_a_resend_with_other_content_is_a_conflict(actor, plot, assignee):
    values = data(plot, assignee, id=uuid.uuid4())
    create_activity(actor, values)

    with pytest.raises(ActivityIdConflict):
        create_activity(actor, {**values, "activity_type": ActivityType.PRUNING})


def test_an_id_of_another_producer_is_a_conflict_that_reveals_nothing(actor, plot, assignee):
    foreign = AgriculturalActivityFactory()

    with pytest.raises(ActivityIdConflict):
        create_activity(actor, data(plot, assignee, id=foreign.pk))

    foreign.refresh_from_db()
    assert foreign.plot != plot


def test_the_technical_account_schedules_on_any_producer(plot, assignee):
    superuser = UserFactory(is_superuser=True)

    activity, created = create_activity(superuser, data(plot, assignee))

    assert created is True
    assert activity.plot == plot


def test_nothing_is_kept_if_the_history_fails(actor, plot, assignee, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("history down")

    monkeypatch.setattr(audit.AgriculturalActivityAuditEvent, "record", broken)

    with pytest.raises(RuntimeError):
        create_activity(actor, data(plot, assignee))

    assert not AgriculturalActivity.objects.exists()
