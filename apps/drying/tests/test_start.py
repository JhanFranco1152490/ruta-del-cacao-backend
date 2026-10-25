"""Iniciar el secado de un lote fermentado en una marquesina, y lo que pide su formulario."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate
from apps.drying.models import DryingProcess, DryingProcessAuditEvent
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.fermentation.tests.factories import FermentationProcessFactory
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.postharvest_parameters.tests.factories import PostharvestParametersFactory

from .helpers import Farmstead, fermented_lot

pytestmark = pytest.mark.django_db

URL = "/api/drying"
OPTIONS_URL = f"{URL}/start-options"
MANAGE = "drying.manage_drying"
LOGS = "drying.log_drying"


@pytest.fixture
def estate():
    return Farmstead()


def start(client, body):
    return client.post(URL, body, format="json")


# --- Iniciar ---


def test_starting_puts_the_lot_in_the_dryer_and_in_drying(auth_client, estate):
    response = start(auth_client(estate.foreman), estate.start_body())

    assert response.status_code == 201, response.data
    assert response["Location"].endswith(f"/api/drying/{estate.lot.pk}")
    assert response.data["lot"]["status"] == "drying"
    assert response.data["facility"]["name"] == "M-01"
    assert response.data["entry_moisture_out_of_range"] is False
    estate.lot.refresh_from_db()
    estate.dryer.refresh_from_db()
    assert estate.lot.status == LotStatus.DRYING
    assert estate.dryer.current_lot_id == estate.lot.pk
    event = DryingProcessAuditEvent.objects.get(process_id=estate.lot.pk)
    assert (event.action, event.actor) == ("started", estate.foreman)


@pytest.mark.parametrize(
    "missing", ["facility_id", "started_at", "entry_moisture_pct", "responsible_id"]
)
def test_every_start_field_is_required(auth_client, estate, missing):
    body = estate.start_body()
    del body[missing]

    response = start(auth_client(estate.owner), body)

    assert response.status_code == 400
    assert missing in response.data["fields"]
    assert not DryingProcess.objects.exists()


@pytest.mark.parametrize("moisture", ["-0.1", "100.1", "58.55"])
def test_the_entry_moisture_is_a_percentage_with_one_decimal(auth_client, estate, moisture):
    response = start(auth_client(estate.owner), estate.start_body(entry_moisture_pct=moisture))

    assert response.status_code == 400
    assert "entry_moisture_pct" in response.data["fields"]


def test_an_entry_moisture_out_of_the_range_asks_for_confirmation(auth_client, estate):
    client = auth_client(estate.owner)

    refused = start(client, estate.start_body(entry_moisture_pct="48.0"))

    assert refused.status_code == 422
    assert refused.data["code"] == "entry_moisture_out_of_range"
    assert refused.data["range"] == {"min": "55.0", "max": "60.0"}
    assert not DryingProcess.objects.exists()
    estate.dryer.refresh_from_db()
    assert estate.dryer.current_lot_id is None

    confirmed = start(
        client, estate.start_body(entry_moisture_pct="48.0", confirm_entry_moisture=True)
    )

    assert confirmed.status_code == 201
    assert confirmed.data["entry_moisture_out_of_range"] is True


def test_the_range_is_the_producer_s_own(auth_client, estate):
    PostharvestParametersFactory(
        producer=estate.producer,
        entry_moisture_min_pct=Decimal("45.0"),
        entry_moisture_max_pct=Decimal("50.0"),
    )

    response = start(auth_client(estate.owner), estate.start_body(entry_moisture_pct="48.0"))

    assert response.status_code == 201
    assert response.data["entry_moisture_out_of_range"] is False


@pytest.mark.parametrize("edge", ["55.0", "60.0"])
def test_the_edges_of_the_range_are_inside(auth_client, estate, edge):
    response = start(auth_client(estate.owner), estate.start_body(entry_moisture_pct=edge))

    assert response.status_code == 201


@pytest.mark.parametrize(
    "status", [LotStatus.GENERATED, LotStatus.FERMENTING, LotStatus.DRYING, LotStatus.DRIED]
)
def test_only_a_fermented_lot_starts_drying(auth_client, estate, status):
    Lot.objects.filter(pk=estate.lot.pk).update(status=status)

    response = start(auth_client(estate.owner), estate.start_body())

    assert response.status_code == 409
    assert (response.data["code"], response.data["current_status"]) == (
        "lot_invalid_status",
        status,
    )


def test_a_start_in_the_future_is_refused(auth_client, estate):
    future = (timezone.now() + timedelta(minutes=5)).isoformat()

    response = start(auth_client(estate.owner), estate.start_body(started_at=future))

    assert response.status_code == 400
    assert "started_at" in response.data["fields"]


def test_a_start_before_the_lot_was_fermented_is_refused(auth_client, estate):
    fermented_at = estate.lot.audit_events.order_by("-occurred_at").first().occurred_at
    before = (fermented_at - timedelta(minutes=1)).isoformat()

    response = start(auth_client(estate.owner), estate.start_body(started_at=before))

    assert response.status_code == 400
    assert "started_at" in response.data["fields"]


def test_a_fermentation_finished_late_still_lets_the_drying_start_after_its_real_end(
    auth_client, estate
):
    # Se registró hoy que la fermentación terminó hace dos días: el secado puede empezar después
    # de ese fin, aunque el evento del lote diga hoy.
    lot = fermented_lot(estate.plot_a, actor=estate.owner, hours_ago=0)
    ended_at = timezone.now() - timedelta(days=2)
    FermentationProcessFactory(
        lot=lot,
        facility__farm=estate.farm_a,
        started_at=ended_at - timedelta(hours=120),
        ended_at=ended_at,
    )
    client = auth_client(estate.owner)

    before = start(
        client,
        estate.start_body(lot=lot, started_at=(ended_at - timedelta(minutes=1)).isoformat()),
    )
    after = start(
        client, estate.start_body(lot=lot, started_at=(ended_at + timedelta(hours=4)).isoformat())
    )

    assert "started_at" in before.data["fields"]
    assert after.status_code == 201, after.data


@pytest.mark.parametrize("state", ["occupied", "inactive"])
def test_a_dryer_that_is_not_free_is_refused(auth_client, estate, state):
    if state == "occupied":
        other = fermented_lot(estate.plot_a)
        start(auth_client(estate.owner), estate.start_body(lot=other))
    else:
        estate.dryer.is_active = False
        estate.dryer.save()

    response = start(auth_client(estate.owner), estate.start_body())

    assert (response.status_code, response.data["code"]) == (409, "facility_unavailable")
    estate.lot.refresh_from_db()
    assert estate.lot.status == LotStatus.FERMENTED


def test_a_dryer_of_another_farm_is_refused(auth_client, estate):
    elsewhere = estate.new_dryer("M-10", farm=estate.farm_b)

    response = start(auth_client(estate.owner), estate.start_body(facility_id=str(elsewhere.pk)))

    assert (response.status_code, response.data["code"]) == (422, "facility_other_farm")


def test_a_fermentation_box_is_not_a_dryer(auth_client, estate):
    box = PostharvestFacilityFactory(farm=estate.farm_a, name="C-01")

    response = start(auth_client(estate.owner), estate.start_body(facility_id=str(box.pk)))

    assert (response.status_code, response.data["code"]) == (422, "facility_wrong_type")


def test_a_dryer_of_another_producer_does_not_exist(auth_client, estate):
    foreign = PostharvestFacilityFactory(facility_type="solar_dryer", name="M-99")

    response = start(auth_client(estate.owner), estate.start_body(facility_id=str(foreign.pk)))

    assert response.status_code == 404


def test_the_responsible_must_be_able_to_manage_the_drying(auth_client, estate):
    logger = make_delegate(estate.producer, [LOGS], farm=estate.farm_a)
    away = make_delegate(estate.producer, [MANAGE], farm=estate.farm_b)
    client = auth_client(estate.owner)

    for account in (logger, away):
        response = start(client, estate.start_body(responsible_id=str(account.pk)))
        assert (response.status_code, response.data["code"]) == (422, "responsible_not_available")
        assert "responsible_id" in response.data["fields"]


def test_a_responsible_of_another_producer_does_not_exist(auth_client, estate):
    stranger = UserFactory()

    response = start(auth_client(estate.owner), estate.start_body(responsible_id=str(stranger.pk)))

    assert response.status_code == 404


def test_starting_needs_the_manage_permission(auth_client, estate):
    logger = make_delegate(estate.producer, [LOGS], farm=estate.farm_a)

    assert start(auth_client(logger), estate.start_body()).status_code == 403


def test_a_lot_of_another_farm_does_not_exist_for_the_foreman(auth_client, estate):
    lot_b = fermented_lot(estate.plot_b)

    response = start(auth_client(estate.foreman), estate.start_body(lot=lot_b))

    assert response.status_code == 404


# --- Lo que pide el formulario ---


def test_the_options_bring_the_free_dryers_the_responsibles_and_the_range(auth_client, estate):
    estate.new_dryer("M-03", is_active=False)
    PostharvestFacilityFactory(farm=estate.farm_a, name="C-01")

    response = auth_client(estate.owner).get(OPTIONS_URL, {"lot": estate.lot.pk})

    assert response.status_code == 200, response.data
    assert [dryer["name"] for dryer in response.data["facilities"]] == ["M-01", "M-02"]
    assert response.data["facilities"][0]["capacity_kg"] == "800.0"
    assert str(estate.foreman.pk) in {person["id"] for person in response.data["responsibles"]}
    assert response.data["entry_moisture_range"] == {"min": "55.0", "max": "60.0"}
    fermented_at = estate.lot.audit_events.order_by("-occurred_at").first().occurred_at
    assert response.data["earliest_start_at"] == timezone.localtime(fermented_at).isoformat()


def test_the_options_of_a_lot_in_another_state_are_a_conflict(auth_client, estate):
    Lot.objects.filter(pk=estate.lot.pk).update(status=LotStatus.GENERATED)

    response = auth_client(estate.owner).get(OPTIONS_URL, {"lot": estate.lot.pk})

    assert (response.status_code, response.data["code"]) == (409, "lot_invalid_status")


def test_the_options_need_the_manage_permission_and_a_lot(auth_client, estate):
    logger = make_delegate(estate.producer, [LOGS], farm=estate.farm_a)

    assert auth_client(logger).get(OPTIONS_URL, {"lot": estate.lot.pk}).status_code == 403
    assert auth_client(estate.owner).get(OPTIONS_URL).status_code == 400
