from datetime import date, timedelta

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.activities.alerts import evaluate
from apps.activities.choices import ActivityType
from apps.activities.tests.factories import (
    AgriculturalActivityFactory,
    done_activity,
    make_assignee,
)
from apps.common import alerts
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 16)
SCHEDULE = "activities.add_agriculturalactivity"


@pytest.fixture
def farm():
    return FarmFactory(producer=ProducerFactory())


@pytest.fixture
def plot(farm):
    return PlotFactory(farm=farm)


@pytest.fixture
def assignee(farm):
    return make_assignee(farm.producer, farm=farm)


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farm=farm), get_system_role(FOREMAN))


def activity_on(plot, assignee, days_from_today, **kwargs):
    return AgriculturalActivityFactory(
        plot=plot,
        assignee=assignee,
        scheduled_date=TODAY + timedelta(days=days_from_today),
        **kwargs,
    )


def notified(drafts):
    return {(draft.recipient_id, draft.kind, draft.condition_key) for draft in drafts}


def kinds(drafts):
    return {draft.kind for draft in drafts}


# Próxima: un recordatorio por cada día que falta.


@pytest.mark.parametrize("days_before", [2, 1, 0])
def test_an_upcoming_activity_reminds_its_assignee_each_day(plot, assignee, days_before):
    activity = activity_on(plot, assignee, days_before)

    drafts = list(evaluate(TODAY))

    assert notified(drafts) == {
        (
            assignee.pk,
            "activity_upcoming",
            f"{activity.pk}:{activity.scheduled_date}:{days_before}",
        )
    }
    [draft] = drafts
    assert draft.thread_key == f"activity:{activity.pk}"
    assert draft.activity_id == activity.pk
    assert draft.condition_date == activity.scheduled_date


def test_three_days_before_is_too_early(plot, assignee):
    activity_on(plot, assignee, 3)

    assert list(evaluate(TODAY)) == []


def test_a_missed_day_is_not_made_up(plot, assignee):
    # Si la evaluación no corrió anteayer, hoy llega solo el recordatorio de hoy.
    activity = activity_on(plot, assignee, 1)

    assert {draft.condition_key for draft in evaluate(TODAY)} == {
        f"{activity.pk}:{activity.scheduled_date}:1"
    }


def test_the_upcoming_reminder_is_only_for_the_assignee(plot, assignee, farm):
    make_producer_owner(farm.producer)
    foreman_of(farm)
    activity_on(plot, assignee, 1)

    assert {draft.recipient_id for draft in evaluate(TODAY)} == {assignee.pk}


def test_an_inactive_assignee_gets_no_reminder(plot, farm):
    inactive = make_assignee(farm.producer, farm=farm, is_active=False)
    activity_on(plot, inactive, 1)

    assert list(evaluate(TODAY)) == []


# Retrasada y vencida: el responsable y quien puede programar en la finca.


@pytest.mark.parametrize("days_late", [1, 2])
def test_a_delayed_activity_warns_each_of_its_two_days(plot, assignee, days_late):
    activity = activity_on(plot, assignee, -days_late)

    assert notified(evaluate(TODAY)) == {
        (
            assignee.pk,
            "activity_delayed",
            f"{activity.pk}:{activity.scheduled_date}:{days_late}",
        )
    }


@pytest.mark.parametrize("days_late", [3, 40])
def test_an_overdue_activity_warns_once_however_old(plot, assignee, days_late):
    activity = activity_on(plot, assignee, -days_late)

    assert notified(evaluate(TODAY)) == {
        (assignee.pk, "activity_overdue", f"{activity.pk}:{activity.scheduled_date}")
    }


def test_the_overdue_key_is_the_same_every_day(plot, assignee):
    activity_on(plot, assignee, -3)

    today = {draft.condition_key for draft in evaluate(TODAY)}
    tomorrow = {draft.condition_key for draft in evaluate(TODAY + timedelta(days=1))}

    assert today == tomorrow


def test_late_warnings_reach_whoever_schedules_on_that_farm(plot, assignee, farm):
    owner = make_producer_owner(farm.producer)
    foreman = foreman_of(farm)
    everywhere = make_delegate(farm.producer, [SCHEDULE], all_farms=True)
    activity_on(plot, assignee, -1)
    activity_on(plot, assignee, -5)

    for kind in ("activity_delayed", "activity_overdue"):
        recipients = {d.recipient_id for d in evaluate(TODAY) if d.kind == kind}
        assert recipients == {assignee.pk, owner.pk, foreman.pk, everywhere.pk}


def test_late_warnings_skip_whoever_cannot_resolve_them(plot, assignee, farm):
    foreman_of(FarmFactory(producer=farm.producer))
    make_delegate(farm.producer, ["activities.view_agriculturalactivity"], farm=farm)
    grant_role(
        UserFactory(producer=farm.producer, farm=farm, is_active=False),
        get_system_role(FOREMAN),
    )
    UserFactory(is_superuser=True, is_staff=True)
    make_producer_owner(ProducerFactory())
    activity_on(plot, assignee, -3)

    assert {draft.recipient_id for draft in evaluate(TODAY)} == {assignee.pk}


def test_an_assignee_who_also_schedules_gets_one_of_each(plot, farm):
    foreman = foreman_of(farm)
    activity_on(plot, foreman, -1)

    drafts = [draft for draft in evaluate(TODAY) if draft.recipient_id == foreman.pk]

    assert len(drafts) == 1


def test_an_inactive_assignee_is_left_out_but_the_others_are_warned(plot, farm):
    inactive = make_assignee(farm.producer, farm=farm, is_active=False)
    foreman = foreman_of(farm)
    activity_on(plot, inactive, -3)

    assert {draft.recipient_id for draft in evaluate(TODAY)} == {foreman.pk}


# Lo que no avisa.


def test_today_without_delay_is_only_the_upcoming_reminder(plot, assignee):
    activity_on(plot, assignee, 0)

    assert kinds(evaluate(TODAY)) == {"activity_upcoming"}


def test_a_done_activity_never_warns(plot, assignee):
    for days in (2, 0, -1, -3, -40):
        done_activity(plot=plot, assignee=assignee, scheduled_date=TODAY + timedelta(days=days))

    assert list(evaluate(TODAY)) == []


@pytest.mark.parametrize(
    "activity_type",
    [ActivityType.PHYTOSANITARY_MONITORING, ActivityType.PHYTOSANITARY_CONTROL],
)
def test_monitorings_and_controls_warn_like_any_activity(plot, assignee, activity_type):
    activity_on(plot, assignee, -3, activity_type=activity_type)

    assert kinds(evaluate(TODAY)) == {"activity_overdue"}


def test_each_activity_is_its_own_thread(plot, assignee):
    first = activity_on(plot, assignee, 1)
    second = activity_on(plot, assignee, 1)

    assert {draft.thread_key for draft in evaluate(TODAY)} == {
        f"activity:{first.pk}",
        f"activity:{second.pk}",
    }


def test_activities_register_their_evaluator():
    assert alerts.evaluators()["activities"] is evaluate


def test_the_recipients_are_found_without_a_query_per_activity(
    plot, assignee, farm, django_assert_max_num_queries
):
    make_producer_owner(farm.producer)
    foreman_of(farm)
    for days in range(-12, 3):
        activity_on(plot, assignee, days)
    activity_on(plot, assignee, -3)

    with django_assert_max_num_queries(12):
        drafts = list(evaluate(TODAY))

    assert len(drafts) > 30
