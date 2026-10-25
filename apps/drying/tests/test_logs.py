"""Registrar, corregir y eliminar la bitácora de un secado en curso."""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.drying.models import DryingLogEntry, DryingProcess, DryingProcessAuditEvent
from apps.drying.services import logs as log_service

from .helpers import Farmstead, fermented_lot

pytestmark = pytest.mark.django_db


@pytest.fixture
def alerts(monkeypatch):
    """Lo que el servicio pasa a la evaluación de desvíos y lo que manda a notificar."""
    seen = {"evaluated": [], "notified": []}

    def evaluate(entry):
        seen["evaluated"].append(entry.pk)
        return [f"aviso de {entry.pk}"]

    monkeypatch.setattr(log_service, "drying_log_alerts", evaluate)
    monkeypatch.setattr(log_service, "notify", lambda drafts: seen["notified"].append(drafts))
    return seen


@pytest.fixture
def place(auth_client, alerts):
    """Un secado iniciado hace tres días a las 14:00, todavía sin bitácora."""
    place = Farmstead()
    place.lot = fermented_lot(place.plot_a, actor=place.owner, hours_ago=120)
    start_day = timezone.localdate() - timedelta(days=3)
    place.started_at = timezone.make_aware(datetime.combine(start_day, time(14, 0)))
    place.start_day = start_day
    body = place.start_body(started_at=place.started_at.isoformat())
    response = auth_client(place.owner).post("/api/drying", body, format="json")
    assert response.status_code == 201, response.data
    return place


def measured(place, day, hour=17):
    """Una hora del día `day` del secado (el 1 es el del inicio)."""
    date = place.start_day + timedelta(days=day - 1)
    return timezone.make_aware(datetime.combine(date, time(hour, 0)))


def log_body(place, day, **overrides):
    body = {
        "id": str(uuid.uuid4()),
        "measured_at": measured(place, day).isoformat(),
        "moisture_pct": "45.0",
        "sun_hours": "5.0",
        "turn_count": 3,
        "turn_frequency_hours": "1.5",
        "weather": "sunny",
    }
    body.update(overrides)
    return body


def register(client, place, body):
    return client.post(f"/api/drying/{place.lot.pk}/logs", body, format="json")


def log_url(place, log_id):
    return f"/api/drying/{place.lot.pk}/logs/{log_id}"


def field_error(response, name):
    assert response.status_code == 400, response.data
    assert response.data["code"] == "validation_error"
    return response.data["fields"][name]


# --- Registrar ---


def test_a_log_is_registered_with_its_day_and_date(auth_client, place, alerts):
    body = log_body(place, 3, notes="Se cubrió a mediodía.")

    response = register(auth_client(place.foreman), place, body)

    assert response.status_code == 201, response.data
    assert response.data["id"] == body["id"]
    assert response.data["day_number"] == 3
    assert response.data["log_date"] == (place.start_day + timedelta(days=2)).isoformat()
    assert response.data["recorded_by"]["id"] == str(place.foreman.pk)
    event = DryingProcessAuditEvent.objects.get(action="log_created")
    assert (event.log_ref, event.actor) == (uuid.UUID(body["id"]), place.foreman)
    assert alerts["evaluated"] == [uuid.UUID(body["id"])]
    assert alerts["notified"] == [[f"aviso de {body['id']}"]]


def test_a_day_without_sun_is_a_day_of_drying(auth_client, place):
    body = log_body(
        place,
        2,
        sun_hours="0.0",
        shade_hours="9.0",
        turn_count=0,
        turn_frequency_hours=None,
        weather="rainy",
    )

    response = register(auth_client(place.owner), place, body)

    assert response.status_code == 201, response.data
    assert (response.data["day_number"], response.data["sun_hours"]) == (2, "0.0")


def test_sending_the_same_log_again_returns_it(auth_client, place, alerts):
    client = auth_client(place.owner)
    body = log_body(place, 1)
    register(client, place, body)

    again = register(client, place, body)

    assert again.status_code == 200
    assert again.data["id"] == body["id"]
    assert DryingLogEntry.objects.count() == 1
    assert len(alerts["evaluated"]) == 1


def test_the_same_id_with_other_data_is_a_conflict(auth_client, place):
    client = auth_client(place.owner)
    body = log_body(place, 1)
    register(client, place, body)

    response = register(client, place, {**body, "moisture_pct": "44.0"})

    assert (response.status_code, response.data["code"]) == (409, "drying_log_id_conflict")


def test_a_second_log_on_the_same_date_is_refused_with_the_first(auth_client, place):
    client = auth_client(place.owner)
    first = register(client, place, log_body(place, 2)).data

    response = register(
        client, place, log_body(place, 2, measured_at=measured(place, 2, hour=9).isoformat())
    )

    assert (response.status_code, response.data["code"]) == (409, "duplicate_drying_log_date")
    assert response.data["existing"] == {"id": first["id"], "day_number": 2}
    assert "measured_at" in response.data["fields"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("moisture_pct", "100.1"),
        ("moisture_pct", "-0.1"),
        ("sun_hours", "24.1"),
        ("shade_hours", "-1.0"),
        ("turn_count", -1),
        ("turn_count", 49),
        ("turn_frequency_hours", "0.4"),
        ("turn_frequency_hours", "24.1"),
        ("weather", "foggy"),
        ("notes", "x" * 501),
    ],
)
def test_a_value_out_of_range_is_refused_with_its_range(auth_client, place, field, value):
    response = register(auth_client(place.owner), place, log_body(place, 2, **{field: value}))

    assert field_error(response, field)


def test_the_messages_say_the_valid_range(auth_client, place):
    client = auth_client(place.owner)

    moisture = register(client, place, log_body(place, 2, moisture_pct="101.0"))
    sun = register(client, place, log_body(place, 2, sun_hours="25.0"))
    turns = register(client, place, log_body(place, 2, turn_count=-1))

    assert field_error(moisture, "moisture_pct") == ["Debe estar entre 0 % y 100 %."]
    assert field_error(sun, "sun_hours") == ["Debe estar entre 0 y 24 horas."]
    assert field_error(turns, "turn_count") == ["No puede ser negativo."]


def test_turns_need_a_frequency_and_no_turns_have_none(auth_client, place):
    client = auth_client(place.owner)

    without = register(client, place, log_body(place, 2, turn_frequency_hours=None))
    extra = register(client, place, log_body(place, 2, turn_count=0))

    assert field_error(without, "turn_frequency_hours")
    assert field_error(extra, "turn_frequency_hours")


def test_the_hours_of_a_day_do_not_exceed_the_drying_hours_of_that_day(auth_client, place):
    client = auth_client(place.owner)
    # El primer día empezó a las 14:00: tuvo 10 horas de secado.
    too_many = register(client, place, log_body(place, 1, sun_hours="8.0", shade_hours="3.0"))

    assert too_many.data["available_hours"] == "10.0"
    assert "10" in field_error(too_many, "sun_hours")[0]

    exact = register(client, place, log_body(place, 1, sun_hours="7.0", shade_hours="3.0"))

    assert exact.status_code == 201, exact.data


@pytest.mark.parametrize("moment", ["before", "future"])
def test_a_measurement_outside_the_drying_is_refused(auth_client, place, moment):
    when = place.started_at - timedelta(minutes=1)
    if moment == "future":
        when = timezone.now() + timedelta(minutes=5)

    response = register(
        auth_client(place.owner), place, log_body(place, 1, measured_at=when.isoformat())
    )

    assert field_error(response, "measured_at")


def test_a_finished_drying_takes_no_more_logs(auth_client, place):
    DryingProcess.objects.filter(pk=place.lot.pk).update(
        ended_at=timezone.now(),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal("300.0"),
        yield_pct=Decimal("36.6"),
        total_sun_hours=Decimal("20.0"),
    )

    response = register(auth_client(place.owner), place, log_body(place, 2))

    assert (response.status_code, response.data["code"]) == (409, "drying_not_in_progress")


def test_the_log_needs_the_log_permission(auth_client, place):
    viewer = make_delegate(place.producer, ["lots.view_lot"], farm=place.farm_a)
    logger = make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_a)
    away = make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_b)

    assert register(auth_client(viewer), place, log_body(place, 2)).status_code == 403
    assert register(auth_client(logger), place, log_body(place, 2)).status_code == 201
    assert register(auth_client(away), place, log_body(place, 3)).status_code == 404


# --- Corregir y eliminar ---


@pytest.fixture
def logged(auth_client, place):
    response = register(auth_client(place.owner), place, log_body(place, 2))
    assert response.status_code == 201, response.data
    return response.data


def test_correcting_a_log_raises_its_version_and_evaluates_again(
    auth_client, place, logged, alerts
):
    response = auth_client(place.owner).patch(
        log_url(place, logged["id"]),
        {"expected_version": logged["version"], "moisture_pct": "38.0"},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert (response.data["moisture_pct"], response.data["version"]) == ("38.0", 2)
    event = DryingProcessAuditEvent.objects.get(action="log_updated")
    assert event.changes == {"moisture_pct": {"before": "45.0", "after": "38.0"}}
    assert alerts["evaluated"] == [uuid.UUID(logged["id"])] * 2


def test_moving_a_log_to_another_date_changes_its_day(auth_client, place, logged):
    response = auth_client(place.owner).patch(
        log_url(place, logged["id"]),
        {"expected_version": logged["version"], "measured_at": measured(place, 3).isoformat()},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["day_number"] == 3


def test_moving_a_log_to_a_date_that_has_one_is_refused(auth_client, place, logged):
    client = auth_client(place.owner)
    register(client, place, log_body(place, 3))

    response = client.patch(
        log_url(place, logged["id"]),
        {"expected_version": logged["version"], "measured_at": measured(place, 3).isoformat()},
        format="json",
    )

    assert (response.status_code, response.data["code"]) == (409, "duplicate_drying_log_date")


def test_a_correction_without_real_changes_keeps_everything(auth_client, place, logged, alerts):
    response = auth_client(place.owner).patch(
        log_url(place, logged["id"]),
        {"expected_version": logged["version"], "moisture_pct": "45.0"},
        format="json",
    )

    assert response.data["version"] == logged["version"]
    assert not DryingProcessAuditEvent.objects.filter(action="log_updated").exists()
    assert len(alerts["evaluated"]) == 1


def test_a_correction_that_breaks_the_turn_rule_is_refused(auth_client, place, logged):
    response = auth_client(place.owner).patch(
        log_url(place, logged["id"]),
        {"expected_version": logged["version"], "turn_count": 0},
        format="json",
    )

    assert field_error(response, "turn_frequency_hours")


def test_a_stale_correction_is_refused_with_the_current_log(auth_client, place, logged):
    response = auth_client(place.owner).patch(
        log_url(place, logged["id"]),
        {"expected_version": logged["version"] + 3, "moisture_pct": "40.0"},
        format="json",
    )

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["id"] == logged["id"]


def test_deleting_a_log_leaves_a_copy_in_the_history(auth_client, place, logged):
    response = auth_client(place.owner).delete(
        f"{log_url(place, logged['id'])}?expected_version={logged['version']}"
    )

    assert response.status_code == 204
    assert not DryingLogEntry.objects.exists()
    event = DryingProcessAuditEvent.objects.get(action="log_deleted")
    assert event.log_ref == uuid.UUID(logged["id"])
    assert event.changes["moisture_pct"] == {"before": "45.0", "after": None}


def test_deleting_needs_the_current_version(auth_client, place, logged):
    client = auth_client(place.owner)

    assert client.delete(log_url(place, logged["id"])).status_code == 400
    stale = client.delete(f"{log_url(place, logged['id'])}?expected_version=9")
    assert (stale.status_code, stale.data["code"]) == (409, "stale_version")


def test_a_log_of_another_drying_is_not_found(auth_client, place, logged):
    other = fermented_lot(place.plot_a, actor=place.owner)
    client = auth_client(place.owner)
    started = client.post(
        "/api/drying",
        place.start_body(lot=other, facility_id=str(place.other_dryer.pk)),
        format="json",
    )
    assert started.status_code == 201, started.data

    response = client.patch(
        f"/api/drying/{other.pk}/logs/{logged['id']}",
        {"expected_version": 1, "moisture_pct": "40.0"},
        format="json",
    )

    assert response.status_code == 404
