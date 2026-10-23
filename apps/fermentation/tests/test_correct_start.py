"""Corregir el inicio de una fermentación que todavía no tiene volteos."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.lots.choices import LotStatus

from .factories import FermentationTurnFactory
from .helpers import Farmstead

pytestmark = pytest.mark.django_db


@pytest.fixture
def place(auth_client):
    place = Farmstead()
    response = auth_client(place.owner).post(
        "/api/fermentation", place.start_body(), format="json"
    )
    assert response.status_code == 201, response.data
    return place


def correct(client, place, **body):
    body.setdefault("expected_version", 1)
    return client.patch(f"/api/fermentation/{place.lot.pk}", body, format="json")


def test_moving_to_another_box_frees_the_first_and_takes_the_second(auth_client, place):
    response = correct(auth_client(place.owner), place, facility_id=str(place.other_box.pk))

    assert response.status_code == 200, response.data
    assert response.data["facility"]["name"] == "C-02"
    assert response.data["version"] == 2
    place.box.refresh_from_db()
    place.other_box.refresh_from_db()
    assert place.box.current_lot_id is None
    assert place.other_box.current_lot_id == place.lot.pk
    event = place.lot.fermentation.audit_events.get(action="updated")
    assert event.changes == {
        "facility_id": {"before": str(place.box.pk), "after": str(place.other_box.pk)}
    }


def test_the_start_and_the_responsible_can_be_corrected(auth_client, place):
    earlier = timezone.now() - timedelta(hours=5)

    response = correct(
        auth_client(place.owner),
        place,
        started_at=earlier.isoformat(),
        responsible_id=str(place.owner.pk),
    )

    assert response.status_code == 200, response.data
    assert response.data["responsible"]["id"] == str(place.owner.pk)
    process = place.lot.fermentation
    process.refresh_from_db()
    assert process.started_at == earlier


def test_a_correction_without_real_changes_keeps_the_version(auth_client, place):
    response = correct(auth_client(place.owner), place, facility_id=str(place.box.pk))

    assert response.status_code == 200
    assert response.data["version"] == 1
    assert not place.lot.fermentation.audit_events.filter(action="updated").exists()


def test_with_a_turn_the_start_can_no_longer_be_corrected(auth_client, place):
    FermentationTurnFactory(process=place.lot.fermentation)

    response = correct(auth_client(place.owner), place, facility_id=str(place.other_box.pk))

    assert (response.status_code, response.data["code"]) == (409, "fermentation_has_turns")


def test_a_stale_version_is_refused_with_the_current_fermentation(auth_client, place):
    response = correct(
        auth_client(place.owner), place, expected_version=5, responsible_id=str(place.owner.pk)
    )

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["version"] == 1


def test_moving_to_a_smaller_box_needs_the_confirmation(auth_client, place):
    small = PostharvestFacilityFactory(farm=place.farm_a, name="C-03", capacity_kg=Decimal("300"))
    client = auth_client(place.owner)

    refused = correct(client, place, facility_id=str(small.pk))
    confirmed = correct(client, place, facility_id=str(small.pk), confirm_over_capacity=True)

    assert (refused.status_code, refused.data["code"]) == (422, "lot_exceeds_capacity")
    assert confirmed.status_code == 200
    assert confirmed.data["over_capacity"] is True


def test_a_finished_fermentation_is_not_corrected(auth_client, place):
    process = place.lot.fermentation
    process.ended_at = timezone.now()
    process.save()
    place.lot.status = LotStatus.FERMENTED
    place.lot.save()

    response = correct(auth_client(place.owner), place, responsible_id=str(place.owner.pk))

    assert (response.status_code, response.data["code"]) == (409, "fermentation_not_in_progress")


def test_the_new_start_follows_the_same_rules(auth_client, place):
    future = (timezone.now() + timedelta(hours=1)).isoformat()

    response = correct(auth_client(place.owner), place, started_at=future)

    assert response.status_code == 400
    assert "started_at" in response.data["fields"]


@pytest.mark.parametrize(
    "body",
    [
        {"facility_id": "00000000-0000-0000-0000-000000000000"},
        {"expected_version": 1},
        # La confirmación sola no cambia nada.
        {"expected_version": 1, "confirm_over_capacity": True},
    ],
)
def test_a_correction_needs_the_version_and_a_real_field(auth_client, place, body):
    response = auth_client(place.owner).patch(
        f"/api/fermentation/{place.lot.pk}", body, format="json"
    )

    assert response.status_code == 400


def test_correcting_needs_the_manage_permission(auth_client, place):
    turns_only = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_a)

    response = correct(auth_client(turns_only), place, responsible_id=str(place.owner.pk))

    assert response.status_code == 403
