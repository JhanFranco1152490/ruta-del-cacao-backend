"""La bodega en la historia de un lote: el ingreso, cada cambio de lugar y cada salida que no es
una venta (a la venta la representa su propia etapa), y lo que le queda hoy."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from rest_framework import serializers

from apps.common.contracts.lot_history import LotHistoryStage, LotStock
from apps.common.serializers import full_name

from .choices import ExitReason, Grade
from .models import ONE_DECIMAL, StockBalance, StockEntry, StockExit, StockMove

ZERO = Decimal("0.0")


@dataclass(frozen=True)
class StockEntryData:
    entered_by: str
    warehouse: str
    # Vacía si no se dijo dónde quedó.
    location: str
    g1_kg: Decimal
    g2_kg: Decimal
    # El ingreso tiene su valor vigente; esto dice si se corrigió y cuándo.
    corrected_at: datetime | None


@dataclass(frozen=True)
class StockMoveData:
    moved_by: str
    from_warehouse: str
    from_location: str
    to_warehouse: str
    to_location: str


@dataclass(frozen=True)
class StockExitData:
    created_by: str
    grade: str
    quantity_kg: Decimal
    reason: str
    detail: str
    # Una salida anulada sigue en la historia, con quién la anuló, cuándo y por qué.
    voided_at: datetime | None
    voided_by: str | None
    void_reason: str | None


def _entry_stage(entry) -> LotHistoryStage:
    return LotHistoryStage.on(
        "stock_entry",
        entry.entry_date,
        recorded_at=entry.entered_at,
        data=StockEntryData(
            entered_by=full_name(entry.entered_by),
            warehouse=entry.warehouse.name,
            location=entry.location,
            g1_kg=entry.g1_kg,
            g2_kg=entry.g2_kg,
            corrected_at=entry.corrected_at,
        ),
    )


def _move_stage(move) -> LotHistoryStage:
    return LotHistoryStage.at(
        "stock_move",
        move.moved_at,
        recorded_at=move.moved_at,
        data=StockMoveData(
            moved_by=full_name(move.moved_by),
            from_warehouse=move.from_warehouse.name,
            from_location=move.from_location,
            to_warehouse=move.to_warehouse.name,
            to_location=move.to_location,
        ),
    )


def _exit_stage(stock_exit) -> LotHistoryStage:
    voided = stock_exit.voided_at is not None
    return LotHistoryStage.on(
        "stock_exit",
        stock_exit.exit_date,
        recorded_at=stock_exit.created_at,
        data=StockExitData(
            created_by=full_name(stock_exit.created_by),
            grade=stock_exit.grade,
            quantity_kg=stock_exit.quantity_kg,
            reason=stock_exit.reason,
            detail=stock_exit.detail,
            voided_at=stock_exit.voided_at,
            voided_by=full_name(stock_exit.voided_by) if voided else None,
            void_reason=stock_exit.void_reason if voided else None,
        ),
    )


def warehouse_history(lot_id) -> list[LotHistoryStage]:
    entry = (
        StockEntry.objects.filter(lot_id=lot_id).select_related("warehouse", "entered_by").first()
    )
    if entry is None:
        return []
    moves = (
        StockMove.objects.filter(lot_id=lot_id)
        .select_related("from_warehouse", "to_warehouse", "moved_by")
        .order_by("moved_at", "id")
    )
    exits = (
        StockExit.objects.filter(lot_id=lot_id)
        .exclude(reason=ExitReason.SALE)
        .select_related("created_by", "voided_by")
        .order_by("exit_date", "created_at", "id")
    )
    return [
        _entry_stage(entry),
        *(_move_stage(move) for move in moves),
        *(_exit_stage(stock_exit) for stock_exit in exits),
    ]


def stock_now(lot_id) -> LotStock | None:
    """Lo que le queda hoy al lote por calibre. Todo ingreso deja al menos un saldo (G1 y G2 suman
    más de 0), así que sin saldos el lote no ingresó."""
    available = dict(
        StockBalance.objects.filter(lot_id=lot_id).values_list("grade", "quantity_kg")
    )
    if not available:
        return None
    return LotStock(
        g1_available_kg=available.get(Grade.G1, ZERO),
        g2_available_kg=available.get(Grade.G2, ZERO),
    )


def _kilograms():
    return serializers.DecimalField(max_digits=7, decimal_places=ONE_DECIMAL)


class StockEntryStageSerializer(serializers.Serializer):
    entered_by = serializers.CharField()
    warehouse = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    g1_kg = _kilograms()
    g2_kg = _kilograms()
    corrected_at = serializers.DateTimeField(allow_null=True)


class StockMoveStageSerializer(serializers.Serializer):
    moved_by = serializers.CharField()
    from_warehouse = serializers.CharField()
    from_location = serializers.CharField(allow_blank=True)
    to_warehouse = serializers.CharField()
    to_location = serializers.CharField(allow_blank=True)


class StockExitStageSerializer(serializers.Serializer):
    created_by = serializers.CharField()
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = _kilograms()
    reason = serializers.ChoiceField(choices=ExitReason.choices)
    detail = serializers.CharField(allow_blank=True)
    voided_at = serializers.DateTimeField(allow_null=True)
    voided_by = serializers.CharField(allow_null=True)
    void_reason = serializers.CharField(allow_null=True)
