"""Lo que la venta usa de la bodega: sacar con motivo Venta y devolver lo que sacó al anularse."""

from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from apps.warehouse.choices import ExitReason
from apps.warehouse.exceptions import ExitAlreadyVoided, StockInsufficient
from apps.warehouse.models import StockAuditEvent, StockBalance, StockExit
from apps.warehouse.services.exits import remove_stock

from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return WarehouseEstate()


def balance(lot, grade="g1"):
    return StockBalance.objects.get(lot=lot, grade=grade).quantity_kg


def sell(estate, quantity="150.0", grade="g1"):
    with transaction.atomic():
        return StockExit.remove_for_sale(
            estate.inspector,
            estate.stored,
            grade,
            Decimal(quantity),
            exit_date=timezone.localdate(),
        )


def test_taking_out_for_a_sale_leaves_an_exit_with_the_sale_reason(estate):
    stock_exit = sell(estate)

    assert stock_exit.reason == ExitReason.SALE
    assert (stock_exit.grade, stock_exit.quantity_kg) == ("g1", Decimal("150.0"))
    assert stock_exit.created_by == estate.inspector
    assert balance(estate.stored) == Decimal("100.0")


def test_taking_out_for_a_sale_never_takes_more_than_there_is(estate):
    with pytest.raises(StockInsufficient):
        sell(estate, quantity="250.1")

    assert balance(estate.stored) == Decimal("250.0")
    assert not StockExit.objects.filter(lot=estate.stored).exists()


def test_voiding_a_sale_exit_gives_the_kilograms_back_and_keeps_the_exit(estate):
    stock_exit = sell(estate)

    with transaction.atomic():
        stock_exit.void_for_sale(estate.inspector, "Venta anulada")

    stock_exit.refresh_from_db()
    assert balance(estate.stored) == Decimal("250.0")
    assert (stock_exit.voided_by, stock_exit.void_reason) == (estate.inspector, "Venta anulada")
    assert stock_exit.voided_at is not None
    assert StockAuditEvent.objects.filter(
        lot=estate.stored, action=StockAuditEvent.Action.EXIT_VOIDED
    ).exists()


def test_a_sale_exit_is_not_voided_twice(estate):
    stock_exit = sell(estate)
    with transaction.atomic():
        stock_exit.void_for_sale(estate.inspector, "Venta anulada")

    with pytest.raises(ExitAlreadyVoided), transaction.atomic():
        stock_exit.void_for_sale(estate.inspector, "Otra vez")

    assert balance(estate.stored) == Decimal("250.0")


def test_a_manual_exit_is_not_voided_as_a_sale(estate):
    manual = remove_stock(
        estate.inspector,
        estate.stored,
        "g1",
        Decimal("5.0"),
        exit_date=timezone.localdate(),
        reason="sample",
    )

    with pytest.raises(ValueError), transaction.atomic():
        manual.void_for_sale(estate.inspector, "No es una venta")

    manual.refresh_from_db()
    assert manual.voided_at is None
    assert balance(estate.stored) == Decimal("245.0")


def test_the_balance_is_what_entered_minus_the_exits_in_force_after_selling_and_voiding(estate):
    first = sell(estate, quantity="100.0")
    sell(estate, quantity="40.0")
    sell(estate, quantity="10.0", grade="g2")
    with transaction.atomic():
        first.void_for_sale(estate.inspector, "Venta anulada")

    for grade, entered in (("g1", Decimal("250.0")), ("g2", Decimal("55.2"))):
        in_force = sum(
            (
                stock_exit.quantity_kg
                for stock_exit in StockExit.objects.filter(
                    lot=estate.stored, grade=grade, voided_at__isnull=True
                )
            ),
            Decimal("0"),
        )
        assert balance(estate.stored, grade) == entered - in_force


def test_the_api_still_refuses_to_void_a_sale_exit(auth_client, estate):
    stock_exit = sell(estate)

    response = auth_client(estate.inspector).post(
        f"/api/stock/{estate.stored.pk}/exits/{stock_exit.pk}/void",
        {"reason": "Por la API no"},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "exit_not_voidable"
