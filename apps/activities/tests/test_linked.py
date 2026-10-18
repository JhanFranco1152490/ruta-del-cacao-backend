"""Lo que sanidad hace sobre una actividad por los métodos del modelo: cerrar un monitoreo con su
resultado y crear un control fitosanitario, programado o ya realizado."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.exceptions import (
    ActivityIdConflict,
    AssigneeNotAvailable,
    InputInactive,
    InvalidActivity,
    PlotInactive,
)
from apps.activities.models import AgriculturalActivity, AgriculturalActivityAuditEvent
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory, make_assignee
from apps.inputs.models import InputMovement
from apps.inputs.tests.factories import AgriculturalInputFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

Action = AgriculturalActivityAuditEvent.Action


@pytest.fixture
def plot():
    return PlotFactory(name="P-03")


@pytest.fixture
def actor(plot):
    return make_producer_owner(plot.farm.producer)


@pytest.fixture
def assignee(plot):
    return make_assignee(plot.farm.producer)


def actions_of(activity):
    return list(
        AgriculturalActivityAuditEvent.objects.filter(activity_ref=activity.pk)
        .order_by("occurred_at", "id")
        .values_list("action", flat=True)
    )


# --- Cerrar un monitoreo ------------------------------------------------------------------------


@pytest.fixture
def monitoring(plot):
    activity = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING
    )
    AgriculturalActivity.objects.filter(pk=activity.pk).update(
        created_at=timezone.now() - timedelta(days=5)
    )
    activity.refresh_from_db()
    return activity


def test_a_monitoring_is_closed_with_its_date_and_who_recorded_it(monitoring, actor):
    done_on = today_in_bogota() - timedelta(days=1)

    monitoring.complete_with_result(actor, done_on, captured_at=None)

    monitoring.refresh_from_db()
    assert monitoring.status == ActivityStatus.DONE
    assert monitoring.done_date == done_on
    assert monitoring.completed_by == actor
    assert monitoring.completed_at is not None
    assert monitoring.version == 2
    assert actions_of(monitoring) == [Action.COMPLETED]


@pytest.mark.parametrize("days", [1, -10])
def test_a_monitoring_keeps_the_completion_date_rules(monitoring, actor, days):
    # Ni futura ni anterior a cuando se programó (hace 5 días).
    with pytest.raises(InvalidActivity) as error:
        monitoring.complete_with_result(
            actor, today_in_bogota() + timedelta(days=days), captured_at=None
        )

    assert "done_date" in error.value.fields


# --- Control programado -------------------------------------------------------------------------


def test_a_scheduled_control_appears_as_a_planned_activity(plot, actor, assignee):
    control_id = uuid.uuid4()
    tomorrow = today_in_bogota() + timedelta(days=1)

    control = AgriculturalActivity.schedule_control(actor, plot, control_id, tomorrow, assignee.pk)

    control.refresh_from_db()
    assert control.pk == control_id
    assert control.activity_type == ActivityType.PHYTOSANITARY_CONTROL
    assert (control.status, control.scheduled_date) == (ActivityStatus.SCHEDULED, tomorrow)
    assert control.assignee == assignee
    assert actions_of(control) == [Action.CREATED]


def test_a_control_is_not_scheduled_on_an_inactive_plot(plot, actor, assignee):
    plot.is_active = False
    plot.save()

    with pytest.raises(PlotInactive):
        AgriculturalActivity.schedule_control(
            actor, plot, uuid.uuid4(), today_in_bogota(), assignee.pk
        )


def test_a_control_is_not_scheduled_in_the_past(plot, actor, assignee):
    with pytest.raises(InvalidActivity):
        AgriculturalActivity.schedule_control(
            actor, plot, uuid.uuid4(), today_in_bogota() - timedelta(days=1), assignee.pk
        )


def test_a_scheduled_control_needs_an_assignable_account(plot, actor):
    stranger = make_assignee(PlotFactory().farm.producer)

    with pytest.raises(AssigneeNotAvailable):
        AgriculturalActivity.schedule_control(
            actor, plot, uuid.uuid4(), today_in_bogota(), stranger.pk
        )


def test_an_id_already_used_by_another_activity_is_a_conflict(plot, actor, assignee):
    taken = AgriculturalActivityFactory()

    with pytest.raises(ActivityIdConflict):
        AgriculturalActivity.schedule_control(
            actor, plot, taken.pk, today_in_bogota(), assignee.pk
        )


# --- Control ya realizado -----------------------------------------------------------------------


def stock_movements(item):
    return list(InputMovement.objects.filter(input=item).values_list("kind", "quantity", "note"))


def test_a_done_control_is_created_done_and_discounts_its_inputs(plot, actor):
    item = AgriculturalInputFactory(producer=plot.farm.producer)
    done_on = today_in_bogota() - timedelta(days=2)

    control = AgriculturalActivity.record_done_control(
        actor,
        plot,
        uuid.uuid4(),
        done_on,
        not_before=done_on - timedelta(days=1),
        assignee_id=actor.pk,
        inputs=[{"input_id": item.pk, "quantity": "0.5"}],
        captured_at=None,
    )

    control.refresh_from_db()
    assert control.activity_type == ActivityType.PHYTOSANITARY_CONTROL
    assert control.status == ActivityStatus.DONE
    assert (control.scheduled_date, control.done_date) == (done_on, done_on)
    assert (control.assignee, control.completed_by) == (actor, actor)
    assert [(row.input, row.quantity) for row in control.inputs.all()] == [
        (item, Decimal("0.500"))
    ]
    assert stock_movements(item) == [
        (InputMovement.Kind.CONSUMPTION, Decimal("-0.500"), "Control fitosanitario · P01")
    ]
    assert actions_of(control) == [Action.CREATED, Action.COMPLETED]


def test_a_done_control_is_recorded_on_an_inactive_plot(plot, actor):
    # La labor ya se hizo: como al registrar la realización, no se rechaza.
    plot.is_active = False
    plot.save()

    control = AgriculturalActivity.record_done_control(
        actor,
        plot,
        uuid.uuid4(),
        today_in_bogota(),
        not_before=today_in_bogota(),
        assignee_id=actor.pk,
        inputs=[],
        captured_at=None,
    )

    assert control.status == ActivityStatus.DONE


@pytest.mark.parametrize("days", [1, -3])
def test_a_done_control_is_neither_future_nor_before_its_monitoring(plot, actor, days):
    # El monitoreo se hizo hace dos días.
    with pytest.raises(InvalidActivity) as error:
        AgriculturalActivity.record_done_control(
            actor,
            plot,
            uuid.uuid4(),
            today_in_bogota() + timedelta(days=days),
            not_before=today_in_bogota() - timedelta(days=2),
            assignee_id=actor.pk,
            inputs=[],
            captured_at=None,
        )

    assert "done_date" in error.value.fields
    assert not AgriculturalActivity.objects.exists()


def test_a_done_control_rejects_an_inactive_input(plot, actor):
    item = AgriculturalInputFactory(producer=plot.farm.producer, is_active=False)

    with pytest.raises(InputInactive):
        AgriculturalActivity.record_done_control(
            actor,
            plot,
            uuid.uuid4(),
            today_in_bogota(),
            not_before=today_in_bogota(),
            assignee_id=actor.pk,
            inputs=[{"input_id": item.pk, "quantity": "1"}],
            captured_at=None,
        )

    assert not AgriculturalActivity.objects.exists()
