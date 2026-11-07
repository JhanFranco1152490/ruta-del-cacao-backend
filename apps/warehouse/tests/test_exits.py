"""Registrar la salida de un calibre de un lote en bodega (HU-40)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate
from apps.warehouse.models import StockAuditEvent, StockBalance, StockExit

from .helpers import WarehouseEstate, stored_lot

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return WarehouseEstate()


def url(lot):
    return f"/api/stock/{lot.pk}/exits"


def body(**overrides):
    return {
        "grade": "g1",
        "quantity_kg": "5.0",
        "exit_date": str(timezone.localdate()),
        "reason": "sample",
        **overrides,
    }


def take(client, lot, **overrides):
    return client.post(url(lot), body(**overrides), format="json")


def balance(lot, grade="g1"):
    return StockBalance.objects.get(lot=lot, grade=grade).quantity_kg


# --- CA-01 y CA-02 ---


def test_a_partial_exit_discounts_the_grade_and_records_who_took_it(auth_client, estate):
    lot = estate.stored

    response = take(auth_client(estate.inspector), lot)

    assert response.status_code == 201, response.data
    assert balance(lot) == Decimal("245.0")
    assert balance(lot, "g2") == Decimal("55.2")
    first = response.data["exits"][0]
    assert (first["grade"], first["quantity_kg"], first["reason"]) == ("g1", "5.0", "sample")
    assert first["created_by"]["id"] == str(estate.inspector.pk)
    assert (first["voided"], first["can_void"]) == (None, True)
    assert {b["grade"]: b["quantity_kg"] for b in response.data["balances"]} == {
        "g1": "245.0",
        "g2": "55.2",
    }


def test_a_total_exit_leaves_the_grade_in_zero_and_the_lot_in_the_warehouse(auth_client, estate):
    lot = estate.stored
    client = auth_client(estate.inspector)

    response = take(client, lot, quantity_kg="250.0", reason="shrinkage")

    assert response.status_code == 201, response.data
    assert balance(lot) == Decimal("0.0")
    lot.refresh_from_db()
    assert lot.status == "in_warehouse"
    listed = client.get("/api/stock", {"search": lot.code}).data["results"]
    assert [row["grade"] for row in listed] == ["g2"]


def test_the_exit_leaves_the_history(auth_client, estate):
    lot = estate.stored

    response = take(auth_client(estate.inspector), lot)

    event = StockAuditEvent.objects.get(lot=lot, action="exited")
    assert event.actor == estate.inspector
    assert event.changes["grade"] == {"before": None, "after": "g1"}
    assert event.changes["quantity_kg"] == {"before": None, "after": "5.0"}
    assert event.changes["exit_id"]["after"] == response.data["exits"][0]["id"]


def test_the_exits_come_from_the_newest_to_the_oldest(auth_client, estate):
    client = auth_client(estate.inspector)
    take(client, estate.stored, quantity_kg="1.0")
    response = take(client, estate.stored, quantity_kg="2.0")

    assert [e["quantity_kg"] for e in response.data["exits"]] == ["2.0", "1.0"]


@pytest.mark.parametrize("reason", ["shrinkage", "sample", "reprocessing", "transfer"])
def test_every_manual_reason_is_accepted(auth_client, estate, reason):
    assert take(auth_client(estate.inspector), estate.stored, reason=reason).status_code == 201


def test_other_goes_with_its_detail(auth_client, estate):
    client = auth_client(estate.inspector)

    refused = take(client, estate.stored, reason="other")
    accepted = take(client, estate.stored, reason="other", detail="Donación a la escuela")

    assert refused.status_code == 400
    assert refused.data["fields"]["detail"] == ["Describa el motivo de la salida"]
    assert accepted.status_code == 201
    assert accepted.data["exits"][0]["detail"] == "Donación a la escuela"


# --- CA-03: más de lo disponible ---


def test_taking_more_than_what_is_available_is_refused_and_changes_nothing(auth_client, estate):
    lot = estate.stored

    response = take(auth_client(estate.inspector), lot, quantity_kg="300.0")

    assert (response.status_code, response.data["code"]) == (400, "stock_insufficient")
    assert response.data["available_kg"] == "250.0"
    assert response.data["fields"]["quantity_kg"] == [
        "La cantidad supera lo disponible (250,0 kg)"
    ]
    assert balance(lot) == Decimal("250.0")
    assert not StockExit.objects.filter(lot=lot).exists()
    assert not StockAuditEvent.objects.filter(lot=lot, action="exited").exists()


def test_taking_exactly_one_decimal_more_is_refused(auth_client, estate):
    response = take(auth_client(estate.inspector), estate.stored, quantity_kg="250.1")

    assert (response.status_code, response.data["code"]) == (400, "stock_insufficient")


def test_a_grade_without_stock_has_nothing_to_take(auth_client, estate):
    only_g1, _ = stored_lot(estate.plot_a, estate.warehouse_a, g1="100.0", g2="0.0")

    response = take(auth_client(estate.inspector), only_g1, grade="g2", quantity_kg="1.0")

    assert (response.status_code, response.data["code"]) == (400, "stock_insufficient")
    assert response.data["available_kg"] == "0.0"


def test_what_was_already_taken_counts(auth_client, estate):
    client = auth_client(estate.inspector)
    take(client, estate.stored, quantity_kg="200.0")

    response = take(client, estate.stored, quantity_kg="60.0")

    assert (response.status_code, response.data["available_kg"]) == (400, "50.0")


# --- Campos ---


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"quantity_kg": "0"}, "quantity_kg"),
        ({"quantity_kg": "-1.0"}, "quantity_kg"),
        ({"quantity_kg": "1.25"}, "quantity_kg"),
        ({"quantity_kg": "mucho"}, "quantity_kg"),
        ({"grade": "g3"}, "grade"),
        ({"reason": "sale"}, "reason"),
        ({"reason": "robo"}, "reason"),
        ({"detail": "x" * 301}, "detail"),
    ],
)
def test_invalid_values_are_refused(auth_client, estate, overrides, field):
    response = take(auth_client(estate.inspector), estate.stored, **overrides)

    assert response.status_code == 400
    assert field in response.data["fields"]
    assert balance(estate.stored) == Decimal("250.0")


@pytest.mark.parametrize("missing", ["grade", "quantity_kg", "exit_date", "reason"])
def test_a_missing_field_is_named(auth_client, estate, missing):
    payload = body()
    del payload[missing]

    response = auth_client(estate.inspector).post(url(estate.stored), payload, format="json")

    assert response.status_code == 400
    assert response.data["fields"][missing] == ["Este campo es requerido."]


def test_an_unknown_field_is_refused(auth_client, estate):
    response = take(auth_client(estate.inspector), estate.stored, notes="otro")

    assert response.status_code == 400


# --- Fecha ---


def test_the_exit_may_be_on_the_day_of_the_entry(auth_client, estate):
    entry_day = estate.entry.entry_date

    response = take(auth_client(estate.inspector), estate.stored, exit_date=str(entry_day))

    assert response.status_code == 201, response.data


def test_a_future_date_is_refused(auth_client, estate):
    tomorrow = timezone.localdate() + timedelta(days=1)

    response = take(auth_client(estate.inspector), estate.stored, exit_date=str(tomorrow))

    assert response.status_code == 400
    assert response.data["fields"]["exit_date"] == ["La fecha no puede ser futura"]


def test_a_date_before_the_entry_is_refused(auth_client, estate):
    before = estate.entry.entry_date - timedelta(days=1)

    response = take(auth_client(estate.inspector), estate.stored, exit_date=str(before))

    assert response.status_code == 400
    assert response.data["fields"]["exit_date"] == [
        "La fecha no puede ser anterior al ingreso del lote"
    ]
    assert balance(estate.stored) == Decimal("250.0")


# --- El lote, permisos y alcance ---


def test_a_lot_that_is_not_in_the_warehouse_answers_its_status(auth_client, estate):
    response = take(auth_client(estate.inspector), estate.classified)

    assert (response.status_code, response.data["code"]) == (409, "lot_invalid_status")
    assert response.data["current_status"] == "classified"


def test_it_needs_a_session(anonymous_client, estate):
    assert anonymous_client.post(url(estate.stored), body(), format="json").status_code == 401


def test_without_the_permission_it_is_forbidden(auth_client, estate):
    viewer = make_delegate(estate.producer, ["warehouse.view_stock"], farm=estate.farm_a)

    assert take(auth_client(viewer), estate.stored).status_code == 403
    assert balance(estate.stored) == Decimal("250.0")


def test_an_employee_of_another_farm_does_not_reach_the_lot(auth_client, estate):
    other = make_delegate(estate.producer, ["warehouse.register_exit"], farm=estate.farm_b)

    assert take(auth_client(other), estate.stored).status_code == 404


def test_the_owner_can_take_too(auth_client, estate):
    assert take(auth_client(estate.owner), estate.stored).status_code == 201
