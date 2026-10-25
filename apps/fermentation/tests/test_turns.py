"""Registrar, corregir y eliminar volteos de una fermentación en curso."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.fermentation.models import FermentationTurn
from apps.lots.choices import LotStatus

from .helpers import Farmstead

pytestmark = pytest.mark.django_db


@pytest.fixture
def place(auth_client):
    """Una fermentación iniciada hace 60 horas en C-01, todavía sin volteos."""
    place = Farmstead()
    place.started_at = (timezone.now() - timedelta(hours=60)).replace(second=0, microsecond=0)
    body = place.start_body(started_at=place.started_at.isoformat())
    response = auth_client(place.owner).post("/api/fermentation", body, format="json")
    assert response.status_code == 201, response.data
    return place


def turn_body(place, hours, **overrides):
    body = {
        "id": str(uuid.uuid4()),
        "turned_at": (place.started_at + timedelta(hours=hours)).isoformat(),
        "temperature_c": "45.0",
        "ph": "4.90",
    }
    body.update(overrides)
    return body


def register(client, place, body):
    return client.post(f"/api/fermentation/{place.lot.pk}/turns", body, format="json")


def turns_url(place, turn_id):
    return f"/api/fermentation/{place.lot.pk}/turns/{turn_id}"


def numbers(client, place):
    turns = client.get(f"/api/fermentation/{place.lot.pk}").data["turns"]
    return [(turn["number"], turn["id"]) for turn in turns]


def test_a_turn_is_registered_with_its_number(auth_client, place):
    body = turn_body(place, 48.5, notes="Masa húmeda en el centro.")

    response = register(auth_client(place.foreman), place, body)

    assert response.status_code == 201, response.data
    assert response.data["id"] == body["id"]
    assert (response.data["number"], response.data["hours_since_start"]) == (1, "48.5")
    assert (response.data["temperature_c"], response.data["ph"]) == ("45.0", "4.90")
    assert response.data["recorded_by"]["id"] == str(place.foreman.pk)
    assert response.data["version"] == 1
    event = place.lot.fermentation.audit_events.get(action="turn_created")
    assert str(event.turn_ref) == body["id"]
    assert event.changes["ph"] == {"before": None, "after": "4.90"}


def test_the_seconds_of_the_turn_are_dropped(auth_client, place):
    at = place.started_at + timedelta(hours=30, seconds=42)

    response = register(
        auth_client(place.owner), place, turn_body(place, 0, turned_at=at.isoformat())
    )

    assert response.status_code == 201
    turn = FermentationTurn.objects.get(pk=response.data["id"])
    assert turn.turned_at == at.replace(second=0)


def test_sending_the_same_turn_again_returns_it_without_a_copy(auth_client, place):
    client = auth_client(place.owner)
    body = turn_body(place, 48)

    first = register(client, place, body)
    again = register(client, place, body)
    changed = register(client, place, {**body, "ph": "5.10"})

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.data["id"] == first.data["id"]
    assert FermentationTurn.objects.count() == 1
    assert (changed.status_code, changed.data["code"]) == (409, "turn_id_conflict")


def test_a_late_turn_takes_its_place_by_time(auth_client, place):
    client = auth_client(place.owner)
    later = register(client, place, turn_body(place, 50)).data
    earlier = register(client, place, turn_body(place, 26)).data

    assert earlier["number"] == 1
    assert numbers(client, place) == [(1, earlier["id"]), (2, later["id"])]


def test_two_turns_in_the_same_minute_are_one(auth_client, place):
    client = auth_client(place.owner)
    first = register(client, place, turn_body(place, 48)).data

    response = register(client, place, turn_body(place, 48))

    assert (response.status_code, response.data["code"]) == (409, "duplicate_turn_time")
    assert response.data["existing"] == {"id": first["id"], "number": 1}


@pytest.mark.parametrize(
    ("field", "value"),
    [("temperature_c", "0.1"), ("temperature_c", "80.0"), ("ph", "0.00"), ("ph", "14.00")],
)
def test_the_edges_of_the_ranges_are_valid(auth_client, place, field, value):
    response = register(auth_client(place.owner), place, turn_body(place, 48, **{field: value}))

    assert response.status_code == 201, response.data


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_c", "0.0"),
        ("temperature_c", "-1.0"),
        ("temperature_c", "80.1"),
        ("temperature_c", "45.25"),
        ("ph", "-0.01"),
        ("ph", "14.01"),
        ("ph", "4.855"),
        ("notes", "x" * 501),
    ],
)
def test_a_value_out_of_range_is_refused_on_its_field(auth_client, place, field, value):
    response = register(auth_client(place.owner), place, turn_body(place, 48, **{field: value}))

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert field in response.data["fields"]


def test_the_range_messages_say_what_is_valid(auth_client, place):
    client = auth_client(place.owner)

    hot = register(client, place, turn_body(place, 48, temperature_c="81.0")).data
    acid = register(client, place, turn_body(place, 48, ph="15.00")).data

    assert hot["fields"]["temperature_c"] == [
        "La temperatura debe ser mayor que 0 °C y hasta 80 °C."
    ]
    assert acid["fields"]["ph"] == ["pH válido entre 0 y 14"]


@pytest.mark.parametrize("field", ["id", "turned_at", "temperature_c", "ph"])
def test_every_measure_is_required(auth_client, place, field):
    body = turn_body(place, 48)
    del body[field]

    response = register(auth_client(place.owner), place, body)

    assert response.status_code == 400
    assert field in response.data["fields"]


def test_a_turn_must_fall_between_the_start_and_now(auth_client, place):
    client = auth_client(place.owner)
    before = place.started_at - timedelta(minutes=1)
    future = timezone.now() + timedelta(minutes=5)

    for moment in (before, future):
        response = register(client, place, turn_body(place, 0, turned_at=moment.isoformat()))
        assert response.status_code == 400
        assert "turned_at" in response.data["fields"]
    on_start = register(client, place, turn_body(place, 0))
    assert on_start.status_code == 201


def finish(place):
    process = place.lot.fermentation
    process.ended_at = timezone.now()
    process.save()
    place.lot.status = LotStatus.FERMENTED
    place.lot.save()


def test_a_finished_fermentation_takes_no_more_turns(auth_client, place):
    finish(place)

    response = register(auth_client(place.owner), place, turn_body(place, 48))

    assert (response.status_code, response.data["code"]) == (409, "fermentation_not_in_progress")


def test_turning_needs_the_turns_permission_and_the_lot_in_reach(auth_client, place):
    viewer = make_delegate(place.producer, ["lots.view_lot"], farm=place.farm_a)
    elsewhere = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_b)
    turns_only = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_a)

    assert register(auth_client(viewer), place, turn_body(place, 48)).status_code == 403
    response = register(auth_client(elsewhere), place, turn_body(place, 48))
    assert (response.status_code, response.data["code"]) == (404, "not_found")
    assert register(auth_client(turns_only), place, turn_body(place, 49)).status_code == 201


# --- Corregir ---


def correct(client, place, turn_id, **body):
    body.setdefault("expected_version", 1)
    return client.patch(turns_url(place, turn_id), body, format="json")


def test_a_turn_is_corrected_with_its_history(auth_client, place):
    client = auth_client(place.owner)
    turn = register(client, place, turn_body(place, 48)).data

    response = correct(client, place, turn["id"], ph="5.20")

    assert response.status_code == 200, response.data
    assert (response.data["ph"], response.data["version"]) == ("5.20", 2)
    event = place.lot.fermentation.audit_events.get(action="turn_updated")
    assert event.changes == {"ph": {"before": "4.90", "after": "5.20"}}


def test_correcting_the_time_can_change_the_order(auth_client, place):
    client = auth_client(place.owner)
    first = register(client, place, turn_body(place, 30)).data
    second = register(client, place, turn_body(place, 50)).data
    later = (place.started_at + timedelta(hours=55)).isoformat()

    response = correct(client, place, first["id"], turned_at=later)

    assert response.data["number"] == 2
    assert numbers(client, place) == [(1, second["id"]), (2, first["id"])]


def test_a_correction_without_real_changes_keeps_the_version(auth_client, place):
    client = auth_client(place.owner)
    turn = register(client, place, turn_body(place, 48)).data

    response = correct(client, place, turn["id"], ph="4.90")

    assert response.data["version"] == 1
    assert not place.lot.fermentation.audit_events.filter(action="turn_updated").exists()


def test_a_correction_follows_the_same_rules(auth_client, place):
    client = auth_client(place.owner)
    turn = register(client, place, turn_body(place, 30)).data
    register(client, place, turn_body(place, 50))
    taken = (place.started_at + timedelta(hours=50)).isoformat()

    stale = correct(client, place, turn["id"], expected_version=3, ph="5.00")
    repeated = correct(client, place, turn["id"], turned_at=taken)
    hot = correct(client, place, turn["id"], temperature_c="90.0")

    assert (stale.status_code, stale.data["code"]) == (409, "stale_version")
    assert stale.data["current"]["id"] == turn["id"]
    assert (repeated.status_code, repeated.data["code"]) == (409, "duplicate_turn_time")
    assert hot.status_code == 400


def test_a_correction_needs_the_version_and_a_field(auth_client, place):
    client = auth_client(place.owner)
    turn = register(client, place, turn_body(place, 48)).data

    without_version = client.patch(turns_url(place, turn["id"]), {"ph": "5.00"}, format="json")
    only_version = correct(client, place, turn["id"])
    with_id = correct(client, place, turn["id"], id=str(uuid.uuid4()))

    assert without_version.status_code == only_version.status_code == with_id.status_code == 400


def test_a_turn_of_another_fermentation_does_not_exist_here(auth_client, place):
    client = auth_client(place.owner)
    other = place.new_lot(100)
    body = place.start_body(lot=other, facility_id=str(place.other_box.pk))
    body["started_at"] = place.started_at.isoformat()
    assert client.post("/api/fermentation", body, format="json").status_code == 201
    foreign = client.post(
        f"/api/fermentation/{other.pk}/turns", turn_body(place, 48), format="json"
    )

    response = correct(client, place, foreign.data["id"], ph="5.00")

    assert (response.status_code, response.data["code"]) == (404, "not_found")


# --- Eliminar ---


def test_deleting_a_turn_renumbers_the_rest_and_leaves_a_copy(auth_client, place):
    client = auth_client(place.owner)
    first = register(client, place, turn_body(place, 30)).data
    second = register(client, place, turn_body(place, 50)).data

    response = client.delete(f"{turns_url(place, first['id'])}?expected_version=1")

    assert response.status_code == 204
    assert numbers(client, place) == [(1, second["id"])]
    event = place.lot.fermentation.audit_events.get(action="turn_deleted")
    assert str(event.turn_ref) == first["id"]
    assert event.changes["ph"] == {"before": "4.90", "after": None}


def test_deleting_needs_the_current_version(auth_client, place):
    client = auth_client(place.owner)
    turn = register(client, place, turn_body(place, 48)).data

    missing = client.delete(turns_url(place, turn["id"]))
    stale = client.delete(f"{turns_url(place, turn['id'])}?expected_version=4")

    assert missing.status_code == 400
    assert (stale.status_code, stale.data["code"]) == (409, "stale_version")
    assert FermentationTurn.objects.filter(pk=turn["id"]).exists()


def test_the_turns_of_a_finished_fermentation_are_read_only(auth_client, place):
    client = auth_client(place.owner)
    turn = register(client, place, turn_body(place, 48)).data
    finish(place)

    corrected = correct(client, place, turn["id"], ph="5.00")
    deleted = client.delete(f"{turns_url(place, turn['id'])}?expected_version=1")

    for response in (corrected, deleted):
        assert (response.status_code, response.data["code"]) == (
            409,
            "fermentation_not_in_progress",
        )
