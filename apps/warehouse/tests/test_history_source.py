from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.common.contracts.lot_history import LotStock, lot_history_source, stage_serializers
from apps.common.serializers import full_name
from apps.harvests.tests.factories import characterized_plot
from apps.lots.tests.factories import LotFactory
from apps.warehouse.history import StockEntryData, StockExitData, StockMoveData
from apps.warehouse.models import StockMove
from apps.warehouse.tests.factories import StockExitFactory, WarehouseFactory
from apps.warehouse.tests.helpers import stored_lot

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")
MOVED = datetime(2026, 4, 10, 11, 0, tzinfo=BOGOTA)


def _history(lot):
    return lot_history_source("warehouse_history")(lot.pk)


def _stored(**kwargs):
    plot = characterized_plot()
    warehouse = WarehouseFactory(farm=plot.farm, name="Bodega principal")
    lot, entry = stored_lot(plot, warehouse, g1="32.5", g2="8.0", location="Estante A2", **kwargs)
    return lot, entry, warehouse


def _move(lot, entry, to_warehouse, *, at=MOVED, to_location="Estante B1"):
    return StockMove.objects.create(
        lot=lot,
        from_warehouse=entry.warehouse,
        from_location="Estante A2",
        to_warehouse=to_warehouse,
        to_location=to_location,
        moved_by=entry.entered_by,
        moved_at=at,
    )


def test_a_lot_that_never_entered_has_no_warehouse_stages_and_no_stock():
    lot = LotFactory()

    assert _history(lot) == []
    assert lot_history_source("stock_now")(lot.pk) is None


def test_the_entry_has_its_date_its_place_and_its_kilograms():
    lot, entry, _ = _stored()

    [stage] = _history(lot)

    assert (stage.kind, stage.occurred_on, stage.occurred_at, stage.recorded_at) == (
        "stock_entry",
        entry.entry_date,
        None,
        entry.entered_at,
    )
    assert stage.data == StockEntryData(
        entered_by=full_name(entry.entered_by),
        warehouse="Bodega principal",
        location="Estante A2",
        g1_kg=Decimal("32.5"),
        g2_kg=Decimal("8.0"),
        corrected_at=None,
    )


def test_a_corrected_entry_says_when_it_was_corrected():
    lot, entry, _ = _stored()
    entry.corrected_by = entry.entered_by
    entry.corrected_at = entry.entered_at + timedelta(hours=3)
    entry.save()

    [stage] = _history(lot)

    assert stage.data.corrected_at == entry.corrected_at


def test_a_move_says_from_where_to_where():
    lot, entry, warehouse = _stored()
    _move(lot, entry, warehouse)

    _, stage = _history(lot)

    assert (stage.kind, stage.occurred_at) == ("stock_move", MOVED)
    assert stage.data == StockMoveData(
        moved_by=full_name(entry.entered_by),
        from_warehouse="Bodega principal",
        from_location="Estante A2",
        to_warehouse="Bodega principal",
        to_location="Estante B1",
    )


def test_an_exit_and_a_voided_exit_are_stages_but_a_sale_exit_is_not():
    lot, entry, _ = _stored()
    sample = StockExitFactory(
        lot=lot, quantity_kg=Decimal("0.5"), exit_date=date(2026, 4, 12), reason="sample"
    )
    voided = StockExitFactory(
        lot=lot,
        quantity_kg=Decimal("1.0"),
        exit_date=date(2026, 4, 15),
        reason="shrinkage",
        voided_by=entry.entered_by,
        voided_at=datetime(2026, 4, 16, 9, 0, tzinfo=BOGOTA),
        void_reason="Registrada por error",
    )
    StockExitFactory(lot=lot, reason="sale")
    StockExitFactory(reason="sample")

    first, second = [stage for stage in _history(lot) if stage.kind == "stock_exit"]

    assert (first.occurred_on, first.occurred_at, first.recorded_at) == (
        date(2026, 4, 12),
        None,
        sample.created_at,
    )
    assert first.data == StockExitData(
        created_by=full_name(sample.created_by),
        grade="g1",
        quantity_kg=Decimal("0.5"),
        reason="sample",
        detail="",
        voided_at=None,
        voided_by=None,
        void_reason=None,
    )
    assert second.occurred_on == date(2026, 4, 15)
    assert (second.data.voided_at, second.data.voided_by, second.data.void_reason) == (
        voided.voided_at,
        full_name(entry.entered_by),
        "Registrada por error",
    )


def test_the_stock_of_today_has_a_grade_that_ran_out_at_zero():
    lot, _, _ = _stored()
    lot.stock_balances.filter(grade="g2").update(quantity_kg=Decimal("0.0"))
    lot.stock_balances.filter(grade="g1").update(quantity_kg=Decimal("12.0"))

    assert lot_history_source("stock_now")(lot.pk) == LotStock(
        g1_available_kg=Decimal("12.0"), g2_available_kg=Decimal("0.0")
    )


def test_a_grade_that_did_not_enter_has_no_stock():
    plot = characterized_plot()
    lot, _ = stored_lot(plot, WarehouseFactory(farm=plot.farm), g1="40.0", g2="0.0")

    assert lot_history_source("stock_now")(lot.pk) == LotStock(
        g1_available_kg=Decimal("40.0"), g2_available_kg=Decimal("0.0")
    )


def test_many_moves_and_exits_take_the_same_queries(django_assert_num_queries):
    lot, entry, warehouse = _stored()
    for hours in range(5):
        _move(lot, entry, warehouse, at=MOVED + timedelta(hours=hours))
    for day in range(10):
        StockExitFactory(lot=lot, exit_date=date(2026, 4, 12) + timedelta(days=day))

    with django_assert_num_queries(3):
        stages = _history(lot)
    with django_assert_num_queries(1):
        lot_history_source("stock_now")(lot.pk)

    assert len(stages) == 16


def test_the_warehouse_stages_are_serialized_with_their_codes():
    lot, entry, warehouse = _stored()
    _move(lot, entry, warehouse)
    StockExitFactory(lot=lot, grade="g2", quantity_kg=Decimal("2"), reason="sample")
    entry_stage, move_stage, exit_stage = _history(lot)
    serializers = stage_serializers()

    assert serializers["stock_entry"].to_representation(entry_stage.data)["g2_kg"] == "8.0"
    assert serializers["stock_move"].to_representation(move_stage.data)["to_location"] == (
        "Estante B1"
    )
    data = serializers["stock_exit"].to_representation(exit_stage.data)
    assert (data["grade"], data["quantity_kg"], data["reason"], data["voided_at"]) == (
        "g2",
        "2.0",
        "sample",
        None,
    )
