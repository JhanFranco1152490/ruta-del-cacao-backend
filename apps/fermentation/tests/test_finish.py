"""Finalizar una fermentación: el lote queda Fermentado y el cajón libre."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.lots.choices import LotStatus

from .helpers import Farmstead

pytestmark = pytest.mark.django_db


@pytest.fixture
def place(auth_client):
    """Una fermentación iniciada hace 122 horas en C-01, con volteos a las 48 y a las 72 horas."""
    place = Farmstead()
    client = auth_client(place.owner)
    place.started_at = (timezone.now() - timedelta(hours=122)).replace(second=0, microsecond=0)
    body = place.start_body(started_at=place.started_at.isoformat())
    assert client.post("/api/fermentation", body, format="json").status_code == 201
    place.last_turn_at = place.started_at + timedelta(hours=72)
    for at in (place.started_at + timedelta(hours=48), place.last_turn_at):
        turn = {"id": str(uuid.uuid4()), "turned_at": at.isoformat(), "temperature_c": "46.0"}
        turn["ph"] = "4.80"
        response = client.post(f"/api/fermentation/{place.lot.pk}/turns", turn, format="json")
        assert response.status_code == 201, response.data
    return place


def finish(client, place, **body):
    body.setdefault("expected_version", 1)
    body.setdefault("ended_at", (place.started_at + timedelta(hours=122)).isoformat())
    return client.post(f"/api/fermentation/{place.lot.pk}/finish", body, format="json")


def test_finishing_leaves_the_lot_fermented_and_the_box_free(auth_client, place):
    response = finish(auth_client(place.foreman), place, notes="Buen olor al corte.")

    assert response.status_code == 200, response.data
    assert response.data["lot"]["status"] == "fermented"
    assert response.data["result"] == {
        "ended_at": timezone.localtime(place.started_at + timedelta(hours=122)).isoformat(),
        "duration_hours": "122.0",
        "turn_count": 2,
        "notes": "Buen olor al corte.",
    }
    assert response.data["next_turn_due_at"] is None
    assert response.data["version"] == 2
    place.lot.refresh_from_db()
    place.box.refresh_from_db()
    assert place.lot.status == LotStatus.FERMENTED
    assert place.box.current_lot_id is None
    process = place.lot.fermentation
    assert process.finished_by == place.foreman
    event = process.audit_events.get(action="finished")
    assert event.changes["end_notes"] == {"before": "", "after": "Buen olor al corte."}


def test_the_lot_leaves_the_event_drying_starts_from(auth_client, place):
    before = timezone.now()

    finish(auth_client(place.owner), place)

    event = place.lot.audit_events.filter(action="status_changed").order_by("-occurred_at").first()
    assert event.changes == {"status": {"before": "fermenting", "after": "fermented"}}
    assert event.occurred_at >= before


def test_the_notes_are_optional_and_have_a_limit(auth_client, place):
    client = auth_client(place.owner)

    too_long = finish(client, place, notes="x" * 501)
    without = finish(client, place)

    assert too_long.status_code == 400
    assert "notes" in too_long.data["fields"]
    assert without.status_code == 200
    assert without.data["result"]["notes"] == ""


def test_the_end_can_be_the_minute_of_the_last_turn(auth_client, place):
    response = finish(auth_client(place.owner), place, ended_at=place.last_turn_at.isoformat())

    assert response.status_code == 200, response.data
    assert response.data["result"]["duration_hours"] == "72.0"


@pytest.mark.parametrize("which", ["before_the_last_turn", "future"])
def test_the_end_must_fall_between_the_last_turn_and_now(auth_client, place, which):
    moment = {
        "before_the_last_turn": place.last_turn_at - timedelta(minutes=1),
        "future": timezone.now() + timedelta(minutes=5),
    }[which]

    response = finish(auth_client(place.owner), place, ended_at=moment.isoformat())

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert "ended_at" in response.data["fields"]
    place.lot.refresh_from_db()
    assert place.lot.status == LotStatus.FERMENTING


def test_without_turns_it_cannot_be_finished(auth_client):
    place = Farmstead()
    client = auth_client(place.owner)
    assert client.post("/api/fermentation", place.start_body(), format="json").status_code == 201

    response = client.post(
        f"/api/fermentation/{place.lot.pk}/finish",
        {"expected_version": 1, "ended_at": timezone.now().isoformat()},
        format="json",
    )

    assert (response.status_code, response.data["code"]) == (409, "fermentation_without_turns")


def test_a_stale_version_is_refused_with_the_current_fermentation(auth_client, place):
    response = finish(auth_client(place.owner), place, expected_version=4)

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["version"] == 1


def test_a_finished_fermentation_is_not_finished_again(auth_client, place):
    client = auth_client(place.owner)
    assert finish(client, place).status_code == 200

    response = finish(client, place, expected_version=2)

    assert (response.status_code, response.data["code"]) == (409, "fermentation_not_in_progress")


def test_the_freed_box_takes_the_next_lot(auth_client, place):
    client = auth_client(place.owner)
    finish(client, place)
    next_lot = place.new_lot(Decimal("300.0"))

    response = client.post("/api/fermentation", place.start_body(lot=next_lot), format="json")

    assert response.status_code == 201, response.data
    assert response.data["facility"]["name"] == "C-01"


def test_if_the_box_cannot_be_freed_nothing_changes(auth_client, place):
    # Alguien dejó el cajón libre por fuera de la aplicación: liberar falla y todo se deshace.
    place.box.current_lot = None
    place.box.occupied_since = None
    place.box.save()

    response = finish(auth_client(place.owner), place)

    assert (response.status_code, response.data["code"]) == (409, "facility_not_occupied_by_lot")
    place.lot.refresh_from_db()
    process = place.lot.fermentation
    process.refresh_from_db()
    assert place.lot.status == LotStatus.FERMENTING
    assert (process.ended_at, process.version) == (None, 1)


def test_finishing_needs_the_manage_permission_and_the_end(auth_client, place):
    turns_only = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_a)

    assert finish(auth_client(turns_only), place).status_code == 403
    # Las sesiones comparten el mismo cliente: se abre la del Productor después.
    missing = auth_client(place.owner).post(
        f"/api/fermentation/{place.lot.pk}/finish", {"expected_version": 1}, format="json"
    )
    assert missing.status_code == 400
    assert "ended_at" in missing.data["fields"]
