"""Sacar cacao de la bodega y anular una salida registrada por error."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..choices import ExitReason
from ..exceptions import (
    ExitAlreadyVoided,
    ExitNotVoidable,
    LotInvalidStatus,
    StockExitNotFound,
    StockInsufficient,
)
from ..models import StockAuditEvent, StockBalance, StockExit
from ..rules import exit_date_errors, exit_detail_errors
from .audit import record_stock_event
from .lots import IN_WAREHOUSE, lock_lot


def _locked_balance(lot, grade) -> StockBalance | None:
    return StockBalance.objects.select_for_update().filter(lot=lot, grade=grade).first()


def remove_stock(
    actor, lot, grade, quantity: Decimal, *, exit_date, reason: str, detail: str = ""
) -> StockExit:
    """Descuenta `quantity` kg del calibre `grade` del lote y deja la salida con su motivo.

    Quien llama (la salida manual de esta app y, más adelante, la venta) ya bloqueó la finca del
    lote y comprobó que está En bodega: aquí solo se aplica la regla. Dentro de ese bloqueo la
    existencia se lee con `select_for_update`, así que nunca sale más de lo que hay.
    """
    if quantity <= 0:
        # La API ya lo rechaza; lo vuelve a cerrar quien llame desde otro lado (la venta).
        raise ValueError("The quantity to take out must be greater than zero.")
    entry = lot.stock_entry
    errors = {
        "exit_date": exit_date_errors(
            exit_date, today=timezone.localdate(), entered_on=entry.entry_date
        ),
        "detail": exit_detail_errors(reason, detail),
    }
    errors = {field: messages for field, messages in errors.items() if messages}
    if errors:
        raise ValidationError(errors)

    balance = _locked_balance(lot, grade)
    available = balance.quantity_kg if balance is not None else Decimal("0.0")
    if quantity > available:
        raise StockInsufficient(available)
    balance.quantity_kg = available - quantity
    balance.save(update_fields=["quantity_kg", "updated_at"])

    stock_exit = StockExit.objects.create(
        lot=lot,
        grade=grade,
        quantity_kg=quantity,
        exit_date=exit_date,
        reason=reason,
        detail=detail,
        created_by=actor,
        created_at=timezone.now(),
    )
    record_stock_event(
        lot=lot,
        actor=actor,
        action=StockAuditEvent.Action.EXITED,
        before={},
        after={
            "exit_id": stock_exit.pk,
            "grade": grade,
            "quantity_kg": quantity,
            "exit_date": exit_date,
            "reason": reason,
            "detail": detail,
        },
        version=entry.version,
    )
    return stock_exit


@transaction.atomic
def register_exit(actor, lot_id, data: dict) -> StockExit:
    """Registra la salida manual de un calibre de un lote En bodega."""
    lot = lock_lot(actor, lot_id)
    if lot.status != IN_WAREHOUSE:
        raise LotInvalidStatus(lot.status)
    return remove_stock(
        actor,
        lot,
        data["grade"],
        data["quantity_kg"],
        exit_date=data["exit_date"],
        reason=data["reason"],
        detail=data.get("detail", ""),
    )


@transaction.atomic
def void_exit(actor, lot_id, exit_id, reason: str) -> StockExit:
    """Anula una salida manual: los kilos vuelven a la existencia y la salida queda en el historial
    con quién la anuló y por qué. Una salida por venta se anula desde la venta."""
    lot = lock_lot(actor, lot_id)
    if lot.status != IN_WAREHOUSE:
        raise LotInvalidStatus(lot.status)
    stock_exit = StockExit.objects.select_for_update().filter(pk=exit_id, lot=lot).first()
    if stock_exit is None:
        raise StockExitNotFound()
    if stock_exit.voided_at is not None:
        raise ExitAlreadyVoided()
    if stock_exit.reason == ExitReason.SALE:
        raise ExitNotVoidable()
    return _give_back(actor, lot, stock_exit, reason)


def void_sale_exit(actor, stock_exit, reason: str) -> StockExit:
    """Anula una salida por venta cuando se anula su venta. Quien llama ya bloqueó la finca del
    lote; aquí solo se aplica la regla."""
    if stock_exit.reason != ExitReason.SALE:
        # Solo la venta llega aquí, y siempre con sus propias salidas.
        raise ValueError("Only a sale exit is voided with its sale.")
    stock_exit = StockExit.objects.select_for_update().get(pk=stock_exit.pk)
    if stock_exit.voided_at is not None:
        raise ExitAlreadyVoided()
    return _give_back(actor, stock_exit.lot, stock_exit, reason)


def _give_back(actor, lot, stock_exit, reason: str) -> StockExit:
    """Devuelve los kilos de la salida a su existencia y la deja anulada con quién y por qué."""
    balance = _locked_balance(lot, stock_exit.grade)
    balance.quantity_kg += stock_exit.quantity_kg
    balance.save(update_fields=["quantity_kg", "updated_at"])

    stock_exit.voided_by = actor
    stock_exit.voided_at = timezone.now()
    stock_exit.void_reason = reason
    stock_exit.save(update_fields=["voided_by", "voided_at", "void_reason"])
    record_stock_event(
        lot=lot,
        actor=actor,
        action=StockAuditEvent.Action.EXIT_VOIDED,
        before={},
        after={"exit_id": stock_exit.pk, "void_reason": reason},
        version=lot.stock_entry.version,
    )
    return stock_exit
