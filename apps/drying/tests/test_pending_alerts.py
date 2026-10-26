"""La bitácora de secado pendiente: un secado en curso sin medición en las últimas 24 horas, en la
evaluación de cada hora, y cuándo deja de valer."""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.common.contracts.alerts import evaluators
from apps.drying.alerts import evaluate
from apps.drying.rules import day_number
from apps.drying.tests.factories import DryingLogEntryFactory, DryingProcessFactory
from apps.lots.choices import LotStatus
from apps.notifications.models import Notification
from apps.notifications.services.evaluate import evaluate_alerts
from apps.notifications.tests.factories import LotNotificationFactory

from .helpers import Farmstead, fermented_lot

pytestmark = pytest.mark.django_db

NOW = timezone.now().replace(second=0, microsecond=0)
LOG_DUE = "drying_log_due"


@pytest.fixture
def place():
    place = Farmstead()
    place.lot.status = LotStatus.DRYING
    place.lot.save(update_fields=["status"])
    place.logger = make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_a)
    place.elsewhere = make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_b)
    return place


def started(place, hours_ago, **fields):
    return DryingProcessFactory(
        lot=place.lot,
        facility=place.dryer,
        responsible=place.foreman,
        started_at=NOW - timedelta(hours=hours_ago),
        **fields,
    )


def measured(process, hours_ago):
    measured_at = NOW - timedelta(hours=hours_ago)
    return DryingLogEntryFactory(
        process=process,
        measured_at=measured_at,
        log_date=timezone.localdate(measured_at),
        day=day_number(timezone.localdate(measured_at), process.started_at),
    )


def drafts(now=NOW):
    return list(evaluate(timezone.localdate(now), now))


# Cuándo falta la bitácora.


def test_a_drying_without_logs_for_24_hours_is_pending_for_everyone(place):
    process = started(place, hours_ago=25)

    found = drafts()

    assert {draft.kind for draft in found} == {LOG_DUE}
    assert {draft.recipient_id for draft in found} == {
        place.owner.pk,
        place.foreman.pk,
        place.logger.pk,
    }
    pending = found[0]
    today = day_number(timezone.localdate(NOW), process.started_at)
    assert pending.condition_key == f"{place.lot.pk}:drying_day:{today}"
    assert pending.thread_key == f"lot:{place.lot.pk}"
    assert pending.lot_id == place.lot.pk
    assert pending.condition_at == process.started_at + timedelta(hours=24)


def test_a_drying_started_less_than_24_hours_ago_is_not_pending(place):
    started(place, hours_ago=23)

    assert drafts() == []


def test_it_counts_the_24_hours_from_the_last_measurement(place):
    process = started(place, hours_ago=80)
    last = measured(process, hours_ago=25)

    pending, *_ = drafts()

    assert pending.condition_at == last.measured_at + timedelta(hours=24)


def test_a_recent_measurement_leaves_nothing_pending(place):
    process = started(place, hours_ago=80)
    measured(process, hours_ago=23)

    assert drafts() == []


def test_a_finished_drying_tells_nothing(place):
    started(
        place,
        hours_ago=100,
        ended_at=NOW - timedelta(hours=30),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal("313.2"),
        yield_pct=Decimal("38.2"),
        total_sun_hours=Decimal("31.5"),
    )

    assert drafts() == []


def test_an_inactive_responsible_is_left_out_but_the_others_are_told(place):
    started(place, hours_ago=25)
    place.foreman.is_active = False
    place.foreman.save(update_fields=["is_active"])

    recipients = {draft.recipient_id for draft in drafts()}

    assert recipients == {place.owner.pk, place.logger.pk}
    assert place.elsewhere.pk not in recipients


def test_more_dryings_of_the_same_producer_add_no_queries(place, django_assert_max_num_queries):
    started(place, hours_ago=30)
    with django_assert_max_num_queries(30) as few:
        drafts()
    for _ in range(3):
        DryingProcessFactory(
            lot=fermented_lot(place.plot_a, actor=place.owner),
            facility=place.new_dryer(f"M-{uuid.uuid4().hex[:4]}"),
            responsible=place.foreman,
            started_at=NOW - timedelta(hours=30),
        )

    with django_assert_max_num_queries(len(few.captured_queries)):
        assert len(drafts()) == 4 * 3


# Por la evaluación de cada hora.


def test_drying_registers_its_evaluator():
    assert evaluators()["drying"] is evaluate


def test_each_day_without_a_log_tells_once_and_replaces_the_previous_day(place):
    started(place, hours_ago=25)
    evaluate_alerts(timezone.localdate(NOW), NOW)
    evaluate_alerts(timezone.localdate(NOW), NOW)
    assert Notification.objects.filter(kind=LOG_DUE, recipient=place.owner).count() == 1

    tomorrow = NOW + timedelta(days=1)
    evaluate_alerts(timezone.localdate(tomorrow), tomorrow)

    notifications = Notification.objects.filter(kind=LOG_DUE, recipient=place.owner)
    assert notifications.count() == 2
    assert notifications.filter(dismissed_at__isnull=True).count() == 1


# Cuándo deja de valer.


@pytest.fixture
def running(auth_client):
    """Un secado iniciado por la API hace cinco días a las 14:00, sin bitácora, con su bitácora
    pendiente."""
    place = Farmstead()
    place.lot = fermented_lot(place.plot_a, actor=place.owner, hours_ago=150)
    place.start_day = timezone.localdate() - timedelta(days=5)
    place.started_at = timezone.make_aware(datetime.combine(place.start_day, time(14, 0)))
    body = place.start_body(started_at=place.started_at.isoformat())
    response = auth_client(place.owner).post("/api/drying", body, format="json")
    assert response.status_code == 201, response.data
    place.pending = LotNotificationFactory(
        lot=place.lot, recipient=place.owner, kind=LOG_DUE, condition_key="day"
    )
    return place


def log_body(place, day):
    measured_at = timezone.make_aware(
        datetime.combine(place.start_day + timedelta(days=day - 1), time(17, 0))
    )
    return {
        "id": str(uuid.uuid4()),
        "measured_at": measured_at.isoformat(),
        "moisture_pct": "30.0",
        "sun_hours": "5.0",
        "turn_count": 0,
        "weather": "sunny",
    }


def post_log(client, place, body):
    response = client.post(f"/api/drying/{place.lot.pk}/logs", body, format="json")
    assert response.status_code in (200, 201), response.data
    return response


def test_registering_a_log_resolves_what_was_pending(
    auth_client, running, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        post_log(auth_client(running.foreman), running, log_body(running, 2))

    running.pending.refresh_from_db()
    assert running.pending.resolved_at is not None


def test_sending_the_same_log_again_resolves_nothing_new(
    auth_client, running, django_capture_on_commit_callbacks
):
    client = auth_client(running.foreman)
    body = log_body(running, 2)
    with django_capture_on_commit_callbacks(execute=True):
        post_log(client, running, body)
    later = LotNotificationFactory(
        lot=running.lot, recipient=running.owner, kind=LOG_DUE, condition_key="later"
    )

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        post_log(client, running, body)

    assert callbacks == []
    later.refresh_from_db()
    assert later.resolved_at is None


def test_finishing_resolves_what_was_pending(
    auth_client, running, django_capture_on_commit_callbacks
):
    client = auth_client(running.foreman)
    post_log(client, running, log_body(running, 2))
    version = client.get(f"/api/drying/{running.lot.pk}").data["version"]

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"/api/drying/{running.lot.pk}/finish",
            {
                "expected_version": version,
                "ended_at": (running.started_at + timedelta(hours=56)).isoformat(),
                "final_moisture_pct": "7.0",
                "dry_weight_kg": "313.2",
            },
            format="json",
        )

    assert response.status_code == 200, response.data
    running.pending.refresh_from_db()
    assert running.pending.resolved_at is not None
