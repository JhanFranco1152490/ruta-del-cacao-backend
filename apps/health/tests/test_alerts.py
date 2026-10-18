from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.common import alerts
from apps.farms.tests.factories import FarmFactory
from apps.health.alerts import evaluate
from apps.health.tests.factories import (
    DetectionFactory,
    PhytosanitaryMonitoringFactory,
    PhytosanitaryTreatmentFactory,
    done_monitoring,
)
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

TODAY = date(2026, 10, 16)
COMPLETE = "activities.complete_agriculturalactivity"


@pytest.fixture
def farm():
    return FarmFactory(producer=ProducerFactory())


@pytest.fixture
def owner(farm):
    return make_producer_owner(farm.producer)


@pytest.fixture
def foreman(farm):
    return grant_role(UserFactory(producer=farm.producer, farm=farm), get_system_role(FOREMAN))


@pytest.fixture
def worker(farm):
    # Registra lo suyo pero no programa: por eso pide el control.
    return make_delegate(farm.producer, [COMPLETE], farm=farm)


def in_bogota(day, hour=9, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def requested(farm, worker, on=TODAY, **kwargs):
    monitoring = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=PlotFactory(farm=farm))
    )
    return DetectionFactory(
        monitoring=monitoring,
        control_requested_by=worker,
        control_requested_at=kwargs.pop("at", in_bogota(on)),
        **kwargs,
    )


def notified(drafts):
    return {(draft.recipient_id, draft.condition_key) for draft in drafts}


@pytest.mark.parametrize("days_ago", [0, 1, 9])
def test_a_requested_control_reminds_every_day_of_its_first_ten(farm, owner, worker, days_ago):
    detection = requested(farm, worker, on=TODAY - timedelta(days=days_ago))

    drafts = list(evaluate(TODAY))

    assert notified(drafts) == {(owner.pk, f"{detection.pk}:{days_ago}")}
    [draft] = drafts
    assert draft.kind == "detection_control_pending"
    assert draft.thread_key == f"detection:{detection.pk}"
    assert draft.detection_id == detection.pk
    assert draft.activity_id == detection.monitoring.activity_id


def test_after_ten_days_it_stops(farm, owner, worker):
    requested(farm, worker, on=TODAY - timedelta(days=10))

    assert list(evaluate(TODAY)) == []


def test_the_days_count_in_bogota(farm, owner, worker):
    # A las 23:30 de Bogotá del día 9 atrás ya es el día siguiente en UTC: sigue contando.
    detection = requested(farm, worker, at=in_bogota(TODAY - timedelta(days=9), 23, 30))

    assert notified(evaluate(TODAY)) == {(owner.pk, f"{detection.pk}:9")}


def test_it_reaches_whoever_can_schedule_on_that_farm(farm, owner, foreman, worker):
    everywhere = make_delegate(
        farm.producer, ["activities.add_agriculturalactivity"], all_farms=True
    )
    requested(farm, worker)

    assert {d.recipient_id for d in evaluate(TODAY)} == {owner.pk, foreman.pk, everywhere.pk}


def test_it_skips_who_asked_and_who_cannot_schedule_there(farm, owner, worker):
    grant_role(
        UserFactory(producer=farm.producer, farm=FarmFactory(producer=farm.producer)),
        get_system_role(FOREMAN),
    )
    make_producer_owner(ProducerFactory())
    requested(farm, worker)

    assert {d.recipient_id for d in evaluate(TODAY)} == {owner.pk}


def test_a_detection_with_a_control_is_not_pending(farm, owner, worker):
    detection = requested(farm, worker)
    PhytosanitaryTreatmentFactory(detection=detection)

    assert list(evaluate(TODAY)) == []


def test_a_detection_that_needs_no_control_is_not_pending(farm, owner, worker):
    requested(farm, worker, control_dismissed_by=owner, control_dismissed_at=timezone.now())

    assert list(evaluate(TODAY)) == []


def test_a_detection_nobody_asked_about_does_not_remind(farm, owner):
    DetectionFactory(monitoring=PhytosanitaryMonitoringFactory())

    assert list(evaluate(TODAY)) == []


def test_health_registers_its_evaluator():
    assert alerts.evaluators()["health"] is evaluate
