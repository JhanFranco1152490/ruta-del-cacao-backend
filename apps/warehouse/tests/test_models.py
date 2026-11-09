"""Las restricciones de la base: lo que ningún servicio puede saltarse."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.warehouse.models import StockBalance, StockEntry, StockExit, Warehouse

from .factories import (
    StockBalanceFactory,
    StockEntryFactory,
    StockExitFactory,
    WarehouseFactory,
)

pytestmark = pytest.mark.django_db


def refused(make):
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


def test_a_warehouse_name_is_unique_in_its_farm_once_normalized():
    farm = FarmFactory()
    WarehouseFactory(farm=farm, name="Bodega Principal", name_normalized="bodegaprincipal")

    refused(
        lambda: WarehouseFactory(
            farm=farm, name="bodega  principal", name_normalized="bodegaprincipal"
        )
    )


def test_the_same_name_is_fine_in_another_farm():
    WarehouseFactory(name="Principal", name_normalized="principal")

    WarehouseFactory(farm=FarmFactory(), name="Principal", name_normalized="principal")

    assert Warehouse.objects.count() == 2


def test_clean_trims_and_normalizes_the_name_and_refuses_a_blank_one():
    warehouse = Warehouse(farm=FarmFactory(), name="  Bodega  Principal ")

    warehouse.clean()

    assert (warehouse.name, warehouse.name_normalized) == ("Bodega  Principal", "bodegaprincipal")
    with pytest.raises(Exception, match="obligatorio"):
        Warehouse(farm=FarmFactory(), name=" - ").clean()
    with pytest.raises(Exception, match="máximo 40"):
        Warehouse(farm=FarmFactory(), name="x" * 41).clean()


@pytest.mark.parametrize(
    "overrides",
    [
        {"g1_kg": Decimal("-1.0")},
        {"g2_kg": Decimal("-0.1")},
        {"g1_kg": Decimal("0.0"), "g2_kg": Decimal("0.0")},
        {"corrected_by": "someone"},
    ],
)
def test_an_entry_refuses_what_it_should(overrides):
    if overrides.get("corrected_by") == "someone":
        overrides = {"corrected_by": UserFactory()}

    refused(lambda: StockEntryFactory(**overrides))


def test_an_entry_can_have_no_location():
    entry = StockEntryFactory(location="")

    assert StockEntry.objects.get(pk=entry.pk).location == ""


def test_an_entry_can_leave_one_grade_in_zero():
    entry = StockEntryFactory(g2_kg=Decimal("0.0"))

    assert StockEntry.objects.get(pk=entry.pk).g1_kg == Decimal("250.0")


def test_a_correction_needs_who_and_when_together():
    entry = StockEntryFactory()

    entry.corrected_by, entry.corrected_at = entry.entered_by, timezone.now()
    entry.save()

    assert StockEntry.objects.get(pk=entry.pk).corrected_at is not None


def test_a_balance_is_unique_per_lot_and_grade_and_never_negative():
    lot = LotFactory(status=LotStatus.IN_WAREHOUSE)
    StockBalanceFactory(lot=lot, grade="g1")

    refused(lambda: StockBalanceFactory(lot=lot, grade="g1"))
    refused(lambda: StockBalanceFactory(lot=lot, grade="g2", quantity_kg=Decimal("-0.1")))
    StockBalanceFactory(lot=lot, grade="g2", quantity_kg=Decimal("0.0"))
    assert StockBalance.objects.filter(lot=lot).count() == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity_kg": Decimal("0.0")},
        {"quantity_kg": Decimal("-1.0")},
        {"reason": "other", "detail": ""},
        {"void_reason": "Era 5 kg, no 50"},
    ],
)
def test_an_exit_refuses_what_it_should(overrides):
    refused(lambda: StockExitFactory(**overrides))


def test_an_exit_voided_needs_who_when_and_why_together():
    exit_ = StockExitFactory()
    exit_.voided_by, exit_.voided_at, exit_.void_reason = (
        exit_.created_by,
        timezone.now(),
        "Era 5 kg, no 50",
    )

    exit_.save()

    assert StockExit.objects.get(pk=exit_.pk).void_reason == "Era 5 kg, no 50"
    exit_.void_reason = ""
    refused(exit_.save)


def test_the_permissions_are_declared_with_a_spanish_name():
    names = dict(Warehouse._meta.permissions)

    assert set(names) == {"view_stock", "register_entry", "register_exit", "manage_warehouse"}
    assert all(label.startswith("Puede") for label in names.values())
