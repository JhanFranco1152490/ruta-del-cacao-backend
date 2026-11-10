"""Anular una salida registrada por error."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.warehouse.models import StockAuditEvent, StockBalance, StockExit
from apps.warehouse.services.exits import remove_stock

from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return WarehouseEstate()


@pytest.fixture
def taken(estate):
    """Una salida de 5,0 kg de G1 por muestra."""
    return StockExit.objects.get(
        pk=remove_stock(
            estate.inspector,
            estate.stored,
            "g1",
            Decimal("5.0"),
            exit_date=timezone.localdate(),
            reason="sample",
        ).pk
    )


def url(lot, stock_exit):
    return f"/api/stock/{lot.pk}/exits/{stock_exit.pk}/void"


def void(client, lot, stock_exit, reason="Era 5 kg, no 50"):
    return client.post(url(lot, stock_exit), {"reason": reason}, format="json")


def balance(lot, grade="g1"):
    return StockBalance.objects.get(lot=lot, grade=grade).quantity_kg


def test_voiding_gives_the_kilograms_back_and_keeps_the_exit(auth_client, estate, taken):
    lot = estate.stored
    assert balance(lot) == Decimal("245.0")

    response = void(auth_client(estate.inspector), lot, taken)

    assert response.status_code == 200, response.data
    assert balance(lot) == Decimal("250.0")
    voided = response.data["exits"][0]
    assert voided["id"] == str(taken.pk)
    assert voided["voided"]["reason"] == "Era 5 kg, no 50"
    assert voided["voided"]["voided_by"]["id"] == str(estate.inspector.pk)
    assert voided["can_void"] is False
    assert StockExit.objects.filter(pk=taken.pk).exists()


def test_voiding_leaves_the_history(auth_client, estate, taken):
    void(auth_client(estate.inspector), estate.stored, taken)

    event = StockAuditEvent.objects.get(lot=estate.stored, action="exit_voided")
    assert event.actor == estate.inspector
    assert event.changes["exit_id"] == {"before": None, "after": str(taken.pk)}
    assert event.changes["void_reason"] == {"before": None, "after": "Era 5 kg, no 50"}


def test_a_grade_taken_entirely_comes_back_when_the_exit_is_voided(auth_client, estate):
    client = auth_client(estate.inspector)
    everything = remove_stock(
        estate.inspector,
        estate.stored,
        "g2",
        Decimal("55.2"),
        exit_date=timezone.localdate(),
        reason="reprocessing",
    )
    assert balance(estate.stored, "g2") == Decimal("0.0")

    void(client, estate.stored, everything)

    assert balance(estate.stored, "g2") == Decimal("55.2")
    listed = client.get("/api/stock", {"search": estate.stored.code}).data["results"]
    assert {row["grade"] for row in listed} == {"g1", "g2"}


def test_voiding_twice_is_refused_and_the_balance_does_not_change(auth_client, estate, taken):
    client = auth_client(estate.inspector)
    void(client, estate.stored, taken)

    response = void(client, estate.stored, taken)

    assert (response.status_code, response.data["code"]) == (409, "exit_already_voided")
    assert balance(estate.stored) == Decimal("250.0")


def test_an_exit_for_a_sale_is_voided_from_the_sale(auth_client, estate):
    sale = remove_stock(
        estate.inspector,
        estate.stored,
        "g1",
        Decimal("10.0"),
        exit_date=timezone.localdate(),
        reason="sale",
    )

    response = void(auth_client(estate.inspector), estate.stored, sale)

    assert (response.status_code, response.data["code"]) == (409, "exit_not_voidable")
    assert balance(estate.stored) == Decimal("240.0")


def test_the_reason_is_required_and_short(auth_client, estate, taken):
    client = auth_client(estate.inspector)

    for reason in ("", "   ", "x" * 301):
        assert void(client, estate.stored, taken, reason=reason).status_code == 400
    assert client.post(url(estate.stored, taken), {}, format="json").status_code == 400
    assert balance(estate.stored) == Decimal("245.0")


def test_an_exit_of_another_lot_does_not_exist(auth_client, estate, taken):
    from .helpers import stored_lot

    other, _ = stored_lot(estate.plot_a, estate.warehouse_a)

    response = void(auth_client(estate.inspector), other, taken)

    assert response.status_code == 404
    assert balance(estate.stored) == Decimal("245.0")


def test_it_needs_a_session_and_the_exit_permission(auth_client, anonymous_client, estate, taken):
    assert (
        anonymous_client.post(
            url(estate.stored, taken), {"reason": "x"}, format="json"
        ).status_code
        == 401
    )
    viewer = make_delegate(estate.producer, ["warehouse.view_stock"], farm=estate.farm_a)
    assert void(auth_client(viewer), estate.stored, taken).status_code == 403
    other = make_delegate(estate.producer, ["warehouse.register_exit"], farm=estate.farm_b)
    assert void(auth_client(other), estate.stored, taken).status_code == 404
