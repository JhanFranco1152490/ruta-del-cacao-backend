"""Mover el cacao de un lote a otra bodega o ubicación de su finca."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.warehouse.models import StockAuditEvent, StockBalance, StockEntry, StockMove
from apps.warehouse.services.exits import remove_stock

from .factories import WarehouseFactory
from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    estate = WarehouseEstate()
    estate.annex = WarehouseFactory(farm=estate.farm_a, name="Anexo", name_normalized="anexo")
    return estate


def url(lot):
    return f"/api/stock/{lot.pk}/move"


def move(client, lot, warehouse, version=1, **fields):
    body = {"expected_version": version, "warehouse_id": str(warehouse.pk), **fields}
    return client.post(url(lot), body, format="json")


def take(estate, grade="g1", quantity="5.0"):
    return remove_stock(
        estate.inspector,
        estate.stored,
        grade,
        Decimal(quantity),
        exit_date=timezone.localdate(),
        reason="sample",
    )


def test_moving_changes_the_place_and_keeps_the_kilograms(auth_client, estate):
    response = move(auth_client(estate.inspector), estate.stored, estate.annex, location="Zona B")

    assert response.status_code == 201, response.data
    entry = response.data["entry"]
    assert (entry["warehouse"]["name"], entry["location"], entry["version"]) == (
        "Anexo",
        "Zona B",
        2,
    )
    balances = StockBalance.objects.filter(lot=estate.stored)
    assert {(b.warehouse_id, b.location) for b in balances} == {(estate.annex.pk, "Zona B")}
    assert {b.grade: b.quantity_kg for b in balances} == {
        "g1": Decimal("250.0"),
        "g2": Decimal("55.2"),
    }


def test_the_move_keeps_where_it_came_from(auth_client, estate):
    response = move(auth_client(estate.inspector), estate.stored, estate.annex)

    (shown,) = response.data["moves"]
    assert shown["from_warehouse"]["name"] == "Bodega A"
    assert shown["from_location"] == "Estante 3"
    assert (shown["to_warehouse"]["name"], shown["to_location"]) == ("Anexo", "")
    assert shown["moved_by"]["id"] == str(estate.inspector.pk)
    assert StockMove.objects.filter(lot=estate.stored).count() == 1


def test_moving_is_allowed_after_cacao_left(auth_client, estate):
    take(estate)

    response = move(auth_client(estate.inspector), estate.stored, estate.annex)

    assert response.status_code == 201, response.data
    assert StockBalance.objects.get(lot=estate.stored, grade="g1").quantity_kg == Decimal("245.0")


def test_moving_inside_the_same_warehouse_changes_only_the_location(auth_client, estate):
    response = move(
        auth_client(estate.inspector), estate.stored, estate.warehouse_a, location="Estante 9"
    )

    assert response.status_code == 201, response.data
    assert response.data["entry"]["location"] == "Estante 9"


def test_moving_leaves_the_history(auth_client, estate):
    move(auth_client(estate.inspector), estate.stored, estate.annex, location="Zona B")

    event = StockAuditEvent.objects.get(lot=estate.stored, action="moved")
    assert event.actor == estate.inspector
    assert event.changes["location"] == {"before": "Estante 3", "after": "Zona B"}


def test_the_same_place_is_refused(auth_client, estate):
    response = move(
        auth_client(estate.inspector), estate.stored, estate.warehouse_a, location="Estante 3"
    )

    assert response.status_code == 400
    assert response.data["code"] == "stock_move_unchanged"
    assert not StockMove.objects.exists()


def test_a_lot_without_cacao_has_nothing_to_move(auth_client, estate):
    take(estate, "g1", "250.0")
    take(estate, "g2", "55.2")

    response = move(auth_client(estate.inspector), estate.stored, estate.annex)

    assert (response.status_code, response.data["code"]) == (409, "lot_without_stock")


def test_the_warehouse_must_be_of_the_farm_and_active(auth_client, estate):
    client = auth_client(estate.owner)
    estate.annex.is_active = False
    estate.annex.save(update_fields=["is_active"])

    other_farm = move(client, estate.stored, estate.warehouse_b)
    inactive = move(client, estate.stored, estate.annex)

    assert other_farm.data["code"] == "warehouse_farm_mismatch"
    assert inactive.data["code"] == "warehouse_inactive"
    assert StockEntry.objects.get(pk=estate.stored.pk).warehouse_id == estate.warehouse_a.pk


def test_a_stale_version_is_a_conflict_with_the_current_lot(auth_client, estate):
    client = auth_client(estate.inspector)
    move(client, estate.stored, estate.annex)

    response = move(client, estate.stored, estate.warehouse_a, version=1)

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["entry"]["version"] == 2


def test_only_a_lot_in_the_warehouse_can_move(auth_client, estate):
    response = move(auth_client(estate.inspector), estate.classified, estate.annex)

    assert (response.status_code, response.data["code"]) == (409, "lot_invalid_status")


def test_a_warehouse_that_received_a_move_is_not_deleted(auth_client, estate):
    move(auth_client(estate.inspector), estate.stored, estate.annex)

    response = auth_client(estate.owner).get("/api/warehouses")

    shown = {row["name"]: row["in_use"] for row in response.data["results"]}
    assert shown["Anexo"] is True


def test_the_entry_permission_is_needed(auth_client, estate):
    reader = make_delegate(estate.producer, ["warehouse.view_stock"], farm=estate.farm_a)

    response = move(auth_client(reader), estate.stored, estate.annex)

    assert response.status_code == 403


def test_a_location_longer_than_sixty_is_refused(auth_client, estate):
    response = move(auth_client(estate.inspector), estate.stored, estate.annex, location="x" * 61)

    assert response.status_code == 400
    assert "location" in response.data["fields"]
