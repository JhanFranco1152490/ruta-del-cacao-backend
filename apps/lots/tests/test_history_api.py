"""La historia de un lote por la API: sus etapas en orden, su estado actual y quién la consulta."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate
from apps.drying.tests.factories import DryingLogEntryFactory
from apps.fermentation.tests.factories import (
    FermentationProcessFactory,
    FermentationTurnFactory,
)
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.lots.tests.journey import Journey
from apps.quality.tests.factories import (
    LotDiscardFactory,
)
from apps.sales.tests.helpers import sale_with_lines

pytestmark = pytest.mark.django_db

PRICE_KEYS = {"price", "price_per_kg", "subtotal", "total", "total_value", "value"}


def _url(lot):
    return f"/api/lots/{lot.pk}/history"


@pytest.fixture
def journey():
    return Journey()


def kinds(response):
    return [stage["kind"] for stage in response.data["stages"]]


def keys_in(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys_in(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(keys_in(item) for item in value))
    return set()


def test_a_sold_lot_shows_every_stage_in_order_with_its_origin(auth_client, journey):
    lot = journey.sold_lot()

    response = auth_client(journey.owner).get(_url(lot))

    assert response.status_code == 200
    assert kinds(response) == [
        "harvest",
        "lot_created",
        "fermentation",
        "drying",
        "evaluation",
        "classification",
        "stock_entry",
        "stock_exit",
        "sale",
        "sale",
    ]
    assert response.data["lot"] == {
        "id": str(lot.pk),
        "code": lot.code,
        "status": "in_warehouse",
        "created_at": response.data["lot"]["created_at"],
    }
    origin = response.data["origin"]
    assert origin["producer"]["member_code"] == "PROD-000123"
    assert origin["producer"]["full_name"] == (
        f"{journey.producer.first_name} {journey.producer.last_name}"
    )
    assert (origin["farm"]["code"], origin["farm"]["name"]) == ("F02", "La Esperanza")
    assert origin["farm"]["municipality"]
    assert (origin["plot"]["code"], origin["plot"]["name"]) == ("P05", "Lote del río")
    assert origin["harvest"] == {
        "id": str(lot.harvest.pk),
        "harvest_date": lot.harvest.harvest_date.isoformat(),
    }
    first = response.data["stages"][0]
    assert first["occurred_at"] is None
    assert first["harvest"]["green_weight_kg"] == "120.0"
    assert response.data["current"] == {
        "status": "in_warehouse",
        "g1_available_kg": "12.0",
        "g2_available_kg": "8.0",
        "sold_kg": "20.0",
    }


def test_each_stage_carries_its_data_under_its_own_kind(auth_client, journey):
    lot = journey.sold_lot()

    stages = auth_client(journey.owner).get(_url(lot)).data["stages"]

    for stage in stages:
        assert set(stage) == {"kind", "occurred_on", "occurred_at", stage["kind"]}
    classification = next(stage for stage in stages if stage["kind"] == "classification")
    assert (
        classification["classification"]["discard_kg"],
        classification["classification"]["discard_reason"],
    ) == (
        "4.5",
        "mold",
    )
    sale, voided = (stage["sale"] for stage in stages if stage["kind"] == "sale")
    assert sale["buyer"] == "Chocolates del Oriente S.A.S."
    assert sale["voided_at"] is None
    assert voided["void_reason"] == "Error de digitación"


def test_the_history_brings_no_price_anywhere(auth_client, journey):
    lot = journey.sold_lot()

    response = auth_client(journey.owner).get(_url(lot))

    assert not PRICE_KEYS & keys_in(response.data)


def test_a_lot_in_process_shows_what_it_has_so_far(auth_client, journey):
    lot = journey.lot(LotStatus.FERMENTING)
    FermentationProcessFactory(lot=lot, started_at=journey.day(1), facility__farm=journey.farm)

    response = auth_client(journey.owner).get(_url(lot))

    assert kinds(response) == ["harvest", "lot_created", "fermentation"]
    assert response.data["stages"][-1]["fermentation"]["ended_at"] is None
    assert response.data["current"] == {
        "status": "fermenting",
        "g1_available_kg": None,
        "g2_available_kg": None,
        "sold_kg": None,
    }


def test_a_whole_discard_shows_its_date_quantity_and_reason_and_nothing_after(
    auth_client, journey
):
    lot = journey.lot(LotStatus.DISCARDED)
    journey.fermented(lot)
    journey.dried(lot, dry_weight="38.5")
    journey.evaluated(lot)
    LotDiscardFactory(lot=lot, discarded_at=journey.day(17), reason="mold")

    response = auth_client(journey.owner).get(_url(lot))

    assert kinds(response)[-2:] == ["evaluation", "discard"]
    discard = response.data["stages"][-1]
    assert discard["occurred_on"] == timezone.localdate(journey.day(17)).isoformat()
    assert (discard["discard"]["quantity_kg"], discard["discard"]["reason"]) == ("38.5", "mold")
    assert response.data["current"]["status"] == "discarded"
    assert response.data["current"]["sold_kg"] is None


def test_a_lot_that_does_not_exist_and_one_of_another_producer_look_the_same(auth_client, journey):
    foreign = LotFactory()
    client = auth_client(journey.owner)

    missing = client.get("/api/lots/00000000-0000-0000-0000-000000000000/history")
    other = client.get(_url(foreign))

    assert (missing.status_code, missing.data["code"]) == (404, "not_found")
    assert (other.status_code, other.data["code"]) == (404, "not_found")


def test_an_employee_sees_the_lots_of_its_farm_only(auth_client, journey):
    lot = journey.lot(LotStatus.GENERATED)
    own = make_delegate(journey.producer, ["lots.view_lot"], farm=journey.farm)
    elsewhere = make_delegate(journey.producer, ["lots.view_lot"], farm=journey.other_farm)

    assert auth_client(own).get(_url(lot)).status_code == 200
    assert auth_client(elsewhere).get(_url(lot)).status_code == 404


def test_without_the_lot_permission_the_history_is_forbidden(auth_client, journey):
    lot = journey.lot(LotStatus.GENERATED)
    employee = make_delegate(journey.producer, ["harvests.view_harvest"], farm=journey.farm)

    response = auth_client(employee).get(_url(lot))

    assert (response.status_code, response.data["code"]) == (403, "permission_denied")


def test_the_technical_account_sees_any_lot(auth_client, journey):
    lot = journey.lot(LotStatus.GENERATED)

    response = auth_client(UserFactory(is_superuser=True)).get(_url(lot))

    assert response.status_code == 200
    assert kinds(response) == ["harvest", "lot_created"]


def test_the_history_is_not_stored(auth_client, journey):
    lot = journey.lot(LotStatus.GENERATED)

    response = auth_client(journey.owner).get(_url(lot))

    assert "no-store" in response["Cache-Control"]


def test_a_long_history_takes_the_same_queries(
    auth_client, journey, django_assert_max_num_queries
):
    lot = journey.sold_lot()
    process = lot.fermentation
    # A la media hora, para no chocar con los volteos que el lote ya tiene a la hora en punto.
    for hours in range(3, 30):
        FermentationTurnFactory(
            process=process, turned_at=journey.day(1, hours) + timedelta(minutes=30)
        )
    for day in range(2, 9):
        DryingLogEntryFactory(process=lot.drying, day=day)
    for days in range(24, 34):
        sale_with_lines(
            journey.farm,
            lines=(("g1", "0.1", 18500),),
            lot=lot,
            sale_date=timezone.localdate(journey.day(days)),
        )
    client = auth_client(journey.owner)

    with django_assert_max_num_queries(HISTORY_QUERIES):
        response = client.get(_url(lot))

    assert len(response.data["stages"]) == 20


# La sesión (la cuenta, su productor y sus permisos: 5), el lote (1) y las fuentes: fermentación
# (2), secado (2), calidad (1), bodega (3), existencias (1), ventas (1) y lo vendido (1).
HISTORY_QUERIES = 17
