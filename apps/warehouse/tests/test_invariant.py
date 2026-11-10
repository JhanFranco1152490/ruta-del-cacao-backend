"""Lo que hay en bodega es lo que entró menos lo que salió, y nunca baja de 0."""

from decimal import Decimal

import pytest
from django.db.models import Sum
from django.utils import timezone

from apps.warehouse.exceptions import ExitAlreadyVoided, StockInsufficient
from apps.warehouse.models import StockBalance, StockEntry, StockExit
from apps.warehouse.services.entry import correct_entry, register_entry
from apps.warehouse.services.exits import register_exit, void_exit

from .factories import WarehouseFactory
from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db


def assert_balances_match_the_movements(lot):
    entry = StockEntry.objects.get(pk=lot.pk)
    for grade, entered in (("g1", entry.g1_kg), ("g2", entry.g2_kg)):
        taken = StockExit.objects.filter(lot=lot, grade=grade, voided_at__isnull=True).aggregate(
            total=Sum("quantity_kg")
        )["total"] or Decimal("0.0")
        balance = StockBalance.objects.filter(lot=lot, grade=grade).first()
        if entered == 0:
            assert balance is None
            continue
        assert balance.quantity_kg >= 0
        assert balance.quantity_kg == entered - taken


def exit_data(grade, quantity):
    return {
        "grade": grade,
        "quantity_kg": Decimal(quantity),
        "exit_date": timezone.localdate(),
        "reason": "shrinkage",
        "detail": "",
    }


def test_a_long_mixed_sequence_always_leaves_the_stock_matching_its_movements():
    estate = WarehouseEstate()
    actor = estate.inspector
    lot = estate.classified
    annex = WarehouseFactory(farm=estate.farm_a, name="Anexo", name_normalized="anexo")

    register_entry(
        actor,
        lot.pk,
        {
            "expected_lot_version": lot.version,
            "entry_date": timezone.localdate(),
            "warehouse_id": estate.warehouse_a.pk,
            "location": "Estante 1",
        },
    )
    assert_balances_match_the_movements(lot)

    correct_entry(actor, lot.pk, 1, {"location": "Estante 2", "warehouse_id": annex.pk})
    assert_balances_match_the_movements(lot)

    first = register_exit(actor, lot.pk, exit_data("g1", "100.0"))
    assert_balances_match_the_movements(lot)
    second = register_exit(actor, lot.pk, exit_data("g1", "150.0"))
    assert_balances_match_the_movements(lot)
    assert StockBalance.objects.get(lot=lot, grade="g1").quantity_kg == Decimal("0.0")

    with pytest.raises(StockInsufficient):
        register_exit(actor, lot.pk, exit_data("g1", "0.1"))
    assert_balances_match_the_movements(lot)

    void_exit(actor, lot.pk, first.pk, "Error")
    assert_balances_match_the_movements(lot)
    with pytest.raises(ExitAlreadyVoided):
        void_exit(actor, lot.pk, first.pk, "Otra vez")
    assert_balances_match_the_movements(lot)

    register_exit(actor, lot.pk, exit_data("g2", "55.2"))
    register_exit(actor, lot.pk, exit_data("g1", "100.0"))
    assert_balances_match_the_movements(lot)

    void_exit(actor, lot.pk, second.pk, "También")
    assert_balances_match_the_movements(lot)
    assert StockBalance.objects.get(lot=lot, grade="g1").quantity_kg == Decimal("150.0")


def test_a_failed_exit_leaves_neither_a_row_nor_a_discount():
    estate = WarehouseEstate()

    with pytest.raises(StockInsufficient):
        register_exit(estate.inspector, estate.stored.pk, exit_data("g1", "999.0"))

    assert not StockExit.objects.filter(lot=estate.stored).exists()
    assert_balances_match_the_movements(estate.stored)


def test_a_failed_correction_leaves_the_stock_where_it_was():
    estate = WarehouseEstate()
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        correct_entry(
            estate.inspector,
            estate.stored.pk,
            1,
            {"location": "Estante 9", "entry_date": timezone.localdate().replace(year=2099)},
        )

    assert {b.location for b in StockBalance.objects.filter(lot=estate.stored)} == {"Estante 3"}
    assert StockEntry.objects.get(pk=estate.stored.pk).location == "Estante 3"


def test_taking_nothing_out_is_a_programming_error():
    estate = WarehouseEstate()
    from apps.warehouse.services.exits import remove_stock

    with pytest.raises(ValueError):
        remove_stock(
            estate.inspector,
            estate.stored,
            "g1",
            Decimal("0.0"),
            exit_date=timezone.localdate(),
            reason="sample",
        )
