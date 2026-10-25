"""Iniciar la fermentación de un lote en un cajón."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate
from apps.facilities.models import PostharvestFacility
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.fermentation.models import FermentationProcess, FermentationProcessAuditEvent
from apps.lots.choices import LotStatus

from .helpers import Farmstead

pytestmark = pytest.mark.django_db


@pytest.fixture
def place():
    return Farmstead()


def start(client, body):
    return client.post("/api/fermentation", body, format="json")


def test_starting_puts_the_lot_in_the_box_and_in_fermentation(auth_client, place):
    body = place.start_body()

    response = start(auth_client(place.foreman), body)

    assert response.status_code == 201, response.data
    assert response["Location"].endswith(f"/api/fermentation/{place.lot.pk}")
    assert response.data["lot"]["status"] == "fermenting"
    assert response.data["facility"]["name"] == "C-01"
    assert response.data["responsible"]["id"] == str(place.foreman.pk)
    assert response.data["over_capacity"] is False
    place.lot.refresh_from_db()
    place.box.refresh_from_db()
    assert place.lot.status == LotStatus.FERMENTING
    assert place.box.current_lot_id == place.lot.pk
    process = FermentationProcess.objects.get(pk=place.lot.pk)
    assert process.created_by == place.foreman
    event = process.audit_events.get()
    assert (event.action, event.actor, event.version) == ("started", place.foreman, 1)
    assert place.lot.audit_events.filter(action="status_changed").exists()


@pytest.mark.parametrize("field", ["facility_id", "started_at", "responsible_id", "lot_id"])
def test_every_field_is_required(auth_client, place, field):
    body = place.start_body()
    del body[field]

    response = start(auth_client(place.owner), body)

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert field in response.data["fields"]


def test_the_start_cannot_be_in_the_future(auth_client, place):
    body = place.start_body(started_at=(timezone.now() + timedelta(minutes=5)).isoformat())

    response = start(auth_client(place.owner), body)

    assert response.status_code == 400
    assert response.data["fields"]["started_at"] == ["No puede ser una fecha futura."]


def test_the_start_cannot_be_before_the_harvest_day(auth_client, place):
    midnight = timezone.make_aware(datetime.combine(place.harvest_day, time.min))

    early = start(
        auth_client(place.owner),
        place.start_body(started_at=(midnight - timedelta(minutes=1)).isoformat()),
    )
    on_time = start(auth_client(place.owner), place.start_body(started_at=midnight.isoformat()))

    assert early.status_code == 400
    assert "started_at" in early.data["fields"]
    assert on_time.status_code == 201


@pytest.mark.parametrize("status", [LotStatus.FERMENTING, LotStatus.FERMENTED, LotStatus.DRYING])
def test_only_a_generated_lot_starts(auth_client, place, status):
    place.lot.status = status
    place.lot.save()

    response = start(auth_client(place.owner), place.start_body())

    assert (response.status_code, response.data["code"]) == (409, "lot_invalid_status")
    assert response.data["current_status"] == status


def test_a_box_already_taken_is_refused_and_nothing_changes(auth_client, place):
    taken = place.new_lot(Decimal("100.0"))
    assert start(auth_client(place.owner), place.start_body(lot=taken)).status_code == 201

    response = start(auth_client(place.owner), place.start_body())

    assert (response.status_code, response.data["code"]) == (409, "facility_unavailable")
    place.lot.refresh_from_db()
    assert place.lot.status == LotStatus.GENERATED
    assert not FermentationProcess.objects.filter(pk=place.lot.pk).exists()


def test_an_inactive_box_is_unavailable(auth_client, place):
    place.box.is_active = False
    place.box.save()

    response = start(auth_client(place.owner), place.start_body())

    assert (response.status_code, response.data["code"]) == (409, "facility_unavailable")


def test_a_dryer_or_a_box_of_another_farm_is_refused(auth_client, place):
    dryer = PostharvestFacilityFactory(
        farm=place.farm_a, name="M-01", facility_type=PostharvestFacility.FacilityType.SOLAR_DRYER
    )
    elsewhere = PostharvestFacilityFactory(farm=place.farm_b, name="C-09")
    client = auth_client(place.owner)

    wrong_type = start(client, place.start_body(facility_id=str(dryer.pk)))
    other_farm = start(client, place.start_body(facility_id=str(elsewhere.pk)))

    assert (wrong_type.status_code, wrong_type.data["code"]) == (422, "facility_wrong_type")
    assert (other_farm.status_code, other_farm.data["code"]) == (422, "facility_other_farm")


def test_a_box_of_another_producer_does_not_exist(auth_client, place):
    foreign = PostharvestFacilityFactory(name="C-77")

    response = start(auth_client(place.owner), place.start_body(facility_id=str(foreign.pk)))

    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_the_responsible_must_be_able_to_ferment_in_the_lot_farm(auth_client, place):
    turns_only = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_a)
    in_farm_b = make_delegate(
        place.producer, ["fermentation.manage_fermentation"], farm=place.farm_b
    )
    stranger = UserFactory()
    client = auth_client(place.owner)

    for account in (turns_only, in_farm_b):
        response = start(client, place.start_body(responsible_id=str(account.pk)))
        assert (response.status_code, response.data["code"]) == (422, "responsible_not_available")
    response = start(client, place.start_body(responsible_id=str(stranger.pk)))
    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_a_lot_heavier_than_the_box_needs_a_confirmation(auth_client, place):
    heavy = place.new_lot(Decimal("820.0"))
    client = auth_client(place.owner)

    refused = start(client, place.start_body(lot=heavy))
    confirmed = start(client, place.start_body(lot=heavy, confirm_over_capacity=True))

    assert (refused.status_code, refused.data["code"]) == (422, "lot_exceeds_capacity")
    assert (refused.data["capacity_kg"], refused.data["green_weight_kg"]) == ("600.0", "820.0")
    assert confirmed.status_code == 201
    assert confirmed.data["over_capacity"] is True


def test_a_lot_that_fills_the_box_exactly_needs_no_confirmation(auth_client, place):
    full = place.new_lot(Decimal("600.0"))

    response = start(auth_client(place.owner), place.start_body(lot=full))

    assert response.status_code == 201
    assert response.data["over_capacity"] is False


def test_starting_needs_the_manage_permission_and_the_lot_in_reach(auth_client, place):
    turns_only = make_delegate(place.producer, ["fermentation.log_turns"], farm=place.farm_a)
    lot_b = place.new_lot(Decimal("100.0"), plot=place.plot_b)

    assert start(auth_client(turns_only), place.start_body()).status_code == 403
    response = start(auth_client(place.foreman), place.start_body(lot=lot_b))
    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_an_unknown_field_is_refused(auth_client, place):
    response = start(auth_client(place.owner), place.start_body(over_capacity=True))

    assert response.status_code == 400
    assert "over_capacity" in response.data["fields"]


def test_the_history_records_who_started_and_how(auth_client, place):
    start(auth_client(place.owner), place.start_body())

    event = FermentationProcessAuditEvent.objects.get(process_id=place.lot.pk)
    assert event.changes["facility_id"]["after"] == str(place.box.pk)
    assert event.changes["responsible_id"]["after"] == str(place.foreman.pk)
