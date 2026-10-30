"""Los volteos pendientes: el recordatorio del primer volteo y el volteo que ya debía estar, en la
evaluación de cada hora, y cuándo dejan de valer."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.common.contracts.alerts import evaluators
from apps.fermentation.alerts import evaluate
from apps.fermentation.tests.factories import FermentationProcessFactory, FermentationTurnFactory
from apps.lots.choices import LotStatus
from apps.notifications.models import Notification
from apps.notifications.services.evaluate import evaluate_alerts
from apps.notifications.tests.factories import LotNotificationFactory
from apps.postharvest_parameters.tests.factories import PostharvestParametersFactory

from .helpers import Farmstead

pytestmark = pytest.mark.django_db

NOW = timezone.now().replace(second=0, microsecond=0)
TODAY = timezone.localdate(NOW)


@pytest.fixture
def place():
    place = Farmstead()
    place.lot.status = LotStatus.FERMENTING
    place.lot.save(update_fields=["status"])
    place.turner = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_a)
    place.elsewhere = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_b)
    return place


def started(place, hours_ago, **fields):
    return FermentationProcessFactory(
        lot=place.lot,
        facility=place.box,
        responsible=place.foreman,
        started_at=NOW - timedelta(hours=hours_ago),
        **fields,
    )


def drafts(now=NOW):
    return list(evaluate(timezone.localdate(now), now))


def by_kind(found, kind):
    return [draft for draft in found if draft.kind == kind]


# El recordatorio del primer volteo.


def test_the_reminder_reaches_only_the_responsible(place):
    process = started(place, hours_ago=42.5)

    (reminder,) = drafts()

    assert reminder.kind == "fermentation_first_turn_due"
    assert reminder.recipient_id == place.foreman.pk
    assert reminder.condition_key == f"{place.lot.pk}:first_turn"
    assert reminder.thread_key == f"lot:{place.lot.pk}"
    assert reminder.lot_id == place.lot.pk
    assert reminder.condition_at == process.started_at + timedelta(hours=48)


@pytest.mark.parametrize(("hours_ago", "expected"), [(41.98, 0), (42, 1), (47.98, 1)])
def test_the_reminder_starts_six_hours_before(place, hours_ago, expected):
    started(place, hours_ago=hours_ago)

    assert len(by_kind(drafts(), "fermentation_first_turn_due")) == expected


def test_an_inactive_responsible_gets_no_reminder_and_nobody_gets_it_instead(place):
    started(place, hours_ago=42.5)
    place.foreman.is_active = False
    place.foreman.save(update_fields=["is_active"])

    assert drafts() == []


def test_the_reminder_follows_the_producer_hours(place):
    PostharvestParametersFactory(producer=place.producer, first_turn_hours=36)
    started(place, hours_ago=31)

    assert [draft.kind for draft in drafts()] == ["fermentation_first_turn_due"]


# El volteo que ya debía estar.


def test_at_48_hours_without_turns_the_first_turn_is_pending_for_everyone(place):
    process = started(place, hours_ago=48)

    found = drafts()

    assert by_kind(found, "fermentation_first_turn_due") == []
    pending = by_kind(found, "fermentation_turn_due")
    assert {draft.recipient_id for draft in pending} == {
        place.owner.pk,
        place.foreman.pk,
        place.turner.pk,
    }
    assert pending[0].condition_key == f"{place.lot.pk}:turn:1"
    assert pending[0].condition_at == process.started_at + timedelta(hours=48)


def test_the_next_turn_is_pending_24_hours_after_the_last(place):
    process = started(place, hours_ago=74)
    FermentationTurnFactory(process=process, turned_at=process.started_at + timedelta(hours=49))

    pending, *_ = found = drafts()

    assert {draft.kind for draft in found} == {"fermentation_turn_due"}
    assert pending.condition_key == f"{place.lot.pk}:turn:2"
    assert pending.condition_at == process.started_at + timedelta(hours=73)
    assert drafts(NOW - timedelta(hours=2)) == []


def test_the_next_turn_follows_the_producer_hours(place):
    PostharvestParametersFactory(producer=place.producer, next_turn_hours=12)
    process = started(place, hours_ago=62)
    FermentationTurnFactory(process=process, turned_at=process.started_at + timedelta(hours=49))

    assert {draft.condition_key for draft in drafts()} == {f"{place.lot.pk}:turn:2"}


def test_a_finished_fermentation_tells_nothing(place):
    started(place, hours_ago=100, ended_at=NOW - timedelta(hours=1))

    assert drafts() == []


def test_the_operator_of_another_farm_is_not_told(place):
    started(place, hours_ago=48)

    assert place.elsewhere.pk not in {draft.recipient_id for draft in drafts()}


def test_it_reads_each_producer_parameters_once(django_assert_max_num_queries):
    places = [Farmstead() for _ in range(3)]
    for place in places:
        for _ in range(2):
            lot = place.new_lot(Decimal("300.0"))
            FermentationProcessFactory(
                lot=lot,
                facility=place.box,
                responsible=place.foreman,
                started_at=NOW - timedelta(hours=50),
            )
    one = Farmstead()
    FermentationProcessFactory(
        lot=one.lot,
        facility=one.box,
        responsible=one.foreman,
        started_at=NOW - timedelta(hours=50),
    )

    with django_assert_max_num_queries(30) as few:
        drafts()
    for _ in range(3):
        lot = one.new_lot(Decimal("300.0"))
        FermentationProcessFactory(
            lot=lot,
            facility=one.box,
            responsible=one.foreman,
            started_at=NOW - timedelta(hours=50),
        )

    # Más fermentaciones del mismo productor no suman consultas.
    with django_assert_max_num_queries(len(few.captured_queries)):
        drafts()


# Por la evaluación de cada hora.


def test_fermentation_registers_its_evaluator():
    assert evaluators()["fermentation"] is evaluate


def test_evaluating_twice_tells_once_and_the_pending_turn_replaces_the_reminder(place):
    started(place, hours_ago=42.5)
    evaluate_alerts(TODAY, NOW)
    evaluate_alerts(TODAY, NOW)

    assert Notification.objects.filter(kind="fermentation_first_turn_due").count() == 1

    later = NOW + timedelta(hours=6)
    evaluate_alerts(timezone.localdate(later), later)

    reminder = Notification.objects.get(kind="fermentation_first_turn_due")
    pending = Notification.objects.get(kind="fermentation_turn_due", recipient=place.foreman)
    assert reminder.dismissed_at is not None
    assert pending.dismissed_at is None


# Cuándo dejan de valer.


@pytest.fixture
def running(auth_client):
    """Una fermentación iniciada por la API hace 50 horas, sin volteos, con su volteo pendiente."""
    place = Farmstead()
    place.started_at = (NOW - timedelta(hours=50)).replace(second=0, microsecond=0)
    body = place.start_body(started_at=place.started_at.isoformat())
    response = auth_client(place.owner).post("/api/fermentation", body, format="json")
    assert response.status_code == 201, response.data
    place.pending = LotNotificationFactory(lot=place.lot, recipient=place.owner)
    return place


def post_turn(client, place, hours):
    body = {
        "id": str(uuid.uuid4()),
        "turned_at": (place.started_at + timedelta(hours=hours)).isoformat(),
        "temperature_c": "45.0",
        "ph": "4.90",
    }
    response = client.post(f"/api/fermentation/{place.lot.pk}/turns", body, format="json")
    assert response.status_code in (200, 201), response.data
    return body


def test_registering_a_turn_resolves_what_was_pending(
    auth_client, running, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        post_turn(auth_client(running.foreman), running, 49)

    running.pending.refresh_from_db()
    assert running.pending.resolved_at is not None


def test_sending_the_same_turn_again_resolves_nothing_new(
    auth_client, running, django_capture_on_commit_callbacks
):
    client = auth_client(running.foreman)
    with django_capture_on_commit_callbacks(execute=True):
        body = post_turn(client, running, 49)
    running.pending.refresh_from_db()
    first = running.pending.resolved_at
    later = LotNotificationFactory(
        lot=running.lot, recipient=running.owner, condition_key=f"{running.lot.pk}:turn:2"
    )

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        client.post(f"/api/fermentation/{running.lot.pk}/turns", body, format="json")

    assert callbacks == []
    later.refresh_from_db()
    assert later.resolved_at is None
    running.pending.refresh_from_db()
    assert running.pending.resolved_at == first


def test_finishing_resolves_what_was_pending(
    auth_client, running, django_capture_on_commit_callbacks
):
    client = auth_client(running.foreman)
    post_turn(client, running, 49)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            f"/api/fermentation/{running.lot.pk}/finish",
            {
                "expected_version": 1,
                "ended_at": (running.started_at + timedelta(hours=50)).isoformat(),
            },
            format="json",
        )

    assert response.status_code == 200, response.data
    running.pending.refresh_from_db()
    assert running.pending.resolved_at is not None


def test_an_old_turn_arriving_late_resolves_and_the_next_one_is_told(
    auth_client, running, django_capture_on_commit_callbacks
):
    # El primer volteo se hizo a las 2 horas de iniciar (llega tarde desde la cola): a las 26 ya
    # tocaba el segundo.
    with django_capture_on_commit_callbacks(execute=True):
        post_turn(auth_client(running.foreman), running, 2)

    running.pending.refresh_from_db()
    assert running.pending.resolved_at is not None
    assert {draft.condition_key for draft in drafts()} == {f"{running.lot.pk}:turn:2"}
