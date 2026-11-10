"""Dos personas que mueven el mismo calibre a la vez."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.tests.concurrency import run_in_parallel
from apps.warehouse.exceptions import StockInsufficient
from apps.warehouse.models import StockBalance, StockExit
from apps.warehouse.services.exits import register_exit

from .helpers import WarehouseEstate

pytestmark = pytest.mark.django_db(transaction=True)


def data(quantity):
    return {
        "grade": "g1",
        "quantity_kg": Decimal(quantity),
        "exit_date": timezone.localdate(),
        "reason": "shrinkage",
        "detail": "",
    }


def test_two_exits_that_do_not_fit_together_leave_one_and_a_refusal():
    estate = WarehouseEstate()

    def take(_):
        try:
            register_exit(estate.inspector, estate.stored.pk, data("200.0"))
            return "taken"
        except StockInsufficient:
            return "insufficient"

    outcomes = run_in_parallel(take, [0, 1])

    assert sorted(outcomes) == ["insufficient", "taken"]
    assert StockBalance.objects.get(lot=estate.stored, grade="g1").quantity_kg == Decimal("50.0")
    assert StockExit.objects.filter(lot=estate.stored).count() == 1


def test_many_small_exits_never_take_more_than_there_is():
    estate = WarehouseEstate()

    def take(_):
        try:
            register_exit(estate.inspector, estate.stored.pk, data("100.0"))
            return "taken"
        except StockInsufficient:
            return "insufficient"

    outcomes = run_in_parallel(take, list(range(4)))

    assert outcomes.count("taken") == 2
    assert StockBalance.objects.get(lot=estate.stored, grade="g1").quantity_kg == Decimal("50.0")
