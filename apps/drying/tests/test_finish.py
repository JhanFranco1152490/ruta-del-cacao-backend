"""Finalizar un secado con su duración y su rendimiento."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.drying.models import DryingProcess, DryingProcessAuditEvent
from apps.drying.services.finish import finish_drying
from apps.lots.choices import LotStatus
from apps.lots.models import Lot

from .helpers import Farmstead, fermented_lot

pytestmark = pytest.mark.django_db


@pytest.fixture
def place(auth_client):
    """Un secado de un lote de 820 kg iniciado hace tres días a las 14:00 en M-01, con la
    bitácora del día 1 (3 h de sol) y del día 2 (8 h de sol, medida a las 16:00)."""
    place = Farmstead()
    place.lot = fermented_lot(place.plot_a, actor=place.owner, hours_ago=120)
    start_day = timezone.localdate() - timedelta(days=3)
    place.started_at = timezone.make_aware(datetime.combine(start_day, time(14, 0)))
    client = auth_client(place.owner)
    started = client.post(
        "/api/drying",
        place.start_body(started_at=place.started_at.isoformat()),
        format="json",
    )
    assert started.status_code == 201, started.data
    place.last_measured_at = place.started_at + timedelta(days=1, hours=2)
    for measured_at, sun in (
        (place.started_at + timedelta(hours=3), "3.0"),
        (place.last_measured_at, "8.0"),
    ):
        logged = client.post(
            f"/api/drying/{place.lot.pk}/logs",
            {
                "id": str(uuid.uuid4()),
                "measured_at": measured_at.isoformat(),
                "moisture_pct": "30.0",
                "sun_hours": sun,
                "turn_count": 0,
                "weather": "sunny",
            },
            format="json",
        )
        assert logged.status_code == 201, logged.data
    place.version = client.get(f"/api/drying/{place.lot.pk}").data["version"]
    return place


def finish_body(place, **overrides):
    # 56 horas desde las 14:00 del día 1: el día 3 a las 22:00, ya pasado.
    body = {
        "expected_version": place.version,
        "ended_at": (place.started_at + timedelta(hours=56)).isoformat(),
        "final_moisture_pct": "7.0",
        "dry_weight_kg": "313.2",
    }
    body.update(overrides)
    return body


def finish(client, place, body):
    return client.post(f"/api/drying/{place.lot.pk}/finish", body, format="json")


def field_error(response, name):
    assert response.status_code == 400, response.data
    return response.data["fields"][name]


def test_finishing_computes_the_yield_and_leaves_the_lot_dry(auth_client, place):
    response = finish(auth_client(place.foreman), place, finish_body(place))

    assert response.status_code == 200, response.data
    assert response.data["lot"]["status"] == "dried"
    assert response.data["result"]["yield_pct"] == "38.2"
    assert response.data["result"]["duration_hours"] == "56.0"
    assert response.data["result"]["days"] == 3
    assert response.data["result"]["total_sun_hours"] == "11.0"
    assert response.data["version"] == place.version + 1
    place.dryer.refresh_from_db()
    assert place.dryer.current_lot_id is None
    assert Lot.objects.get(pk=place.lot.pk).status == LotStatus.DRIED
    process = DryingProcess.objects.get(pk=place.lot.pk)
    assert process.finished_by == place.foreman
    event = DryingProcessAuditEvent.objects.get(action="finished")
    assert event.changes["yield_pct"] == {"before": None, "after": "38.2"}


def test_the_lot_shows_its_dry_weight_after_finishing(auth_client, place):
    client = auth_client(place.owner)
    finish(client, place, finish_body(place))

    drying = client.get(f"/api/lots/{place.lot.pk}").data["drying"]

    assert (drying["dry_weight_kg"], drying["yield_pct"]) == ("313.2", "38.2")


def test_a_drying_can_end_before_a_full_day_after_the_last_measurement(auth_client, place):
    ended_at = place.last_measured_at + timedelta(hours=2)

    response = finish(
        auth_client(place.owner), place, finish_body(place, ended_at=ended_at.isoformat())
    )

    assert response.status_code == 200, response.data


@pytest.mark.parametrize("moment", ["before_last", "future"])
def test_the_end_must_follow_the_last_measurement_and_not_be_future(auth_client, place, moment):
    ended_at = place.last_measured_at - timedelta(minutes=1)
    if moment == "future":
        ended_at = timezone.now() + timedelta(minutes=5)

    response = finish(
        auth_client(place.owner), place, finish_body(place, ended_at=ended_at.isoformat())
    )

    assert field_error(response, "ended_at")


@pytest.mark.parametrize("weight", ["0.0", "-1.0"])
def test_the_dry_weight_must_be_above_zero(auth_client, place, weight):
    response = finish(auth_client(place.owner), place, finish_body(place, dry_weight_kg=weight))

    assert field_error(response, "dry_weight_kg") == ["Debe ser mayor que cero."]


def test_the_dry_weight_cannot_exceed_the_green_weight(auth_client, place):
    response = finish(auth_client(place.owner), place, finish_body(place, dry_weight_kg="820.1"))

    assert field_error(response, "dry_weight_kg") == [
        "No puede ser mayor que el peso en verde (820.0 kg)."
    ]
    assert response.data["green_weight_kg"] == "820.0"


def test_the_whole_green_weight_is_a_hundred_percent(auth_client, place):
    response = finish(auth_client(place.owner), place, finish_body(place, dry_weight_kg="820.0"))

    assert response.data["result"]["yield_pct"] == "100.0"


def test_the_final_moisture_is_a_percentage(auth_client, place):
    response = finish(
        auth_client(place.owner), place, finish_body(place, final_moisture_pct="100.1")
    )

    assert field_error(response, "final_moisture_pct") == ["Debe estar entre 0 % y 100 %."]


def test_a_drying_without_logs_is_not_finished(auth_client, place):
    other = fermented_lot(place.plot_a, actor=place.owner)
    client = auth_client(place.owner)
    started = client.post(
        "/api/drying",
        place.start_body(lot=other, facility_id=str(place.other_dryer.pk)),
        format="json",
    ).data

    response = client.post(
        f"/api/drying/{other.pk}/finish",
        {
            "expected_version": started["version"],
            "ended_at": timezone.now().isoformat(),
            "final_moisture_pct": "7.0",
            "dry_weight_kg": "300.0",
        },
        format="json",
    )

    assert (response.status_code, response.data["code"]) == (409, "drying_without_logs")


def test_a_stale_version_is_refused_with_the_current_drying(auth_client, place):
    response = finish(
        auth_client(place.owner), place, finish_body(place, expected_version=place.version + 5)
    )

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["version"] == place.version


def test_a_finished_drying_is_not_finished_again(auth_client, place):
    client = auth_client(place.owner)
    finished = finish(client, place, finish_body(place)).data

    again = finish(client, place, finish_body(place, expected_version=finished["version"]))

    assert (again.status_code, again.data["code"]) == (409, "drying_not_in_progress")


def test_finishing_needs_the_manage_permission(auth_client, place):
    logger = make_delegate(place.producer, ["drying.log_drying"], farm=place.farm_a)

    assert finish(auth_client(logger), place, finish_body(place)).status_code == 403


def test_a_failure_in_any_step_leaves_everything_as_it_was(monkeypatch, place):
    def broken(*args, **kwargs):
        raise RuntimeError("falla al avanzar el lote")

    monkeypatch.setattr(Lot, "advance_status", broken)

    with pytest.raises(RuntimeError):
        finish_drying(
            place.owner,
            place.lot.pk,
            place.version,
            {
                "ended_at": place.started_at + timedelta(hours=56),
                "final_moisture_pct": 7,
                "dry_weight_kg": 313,
            },
        )

    process = DryingProcess.objects.get(pk=place.lot.pk)
    place.dryer.refresh_from_db()
    assert process.ended_at is None
    assert place.dryer.current_lot_id == place.lot.pk
