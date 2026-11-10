"""Registrar una venta: sus líneas sacan las existencias de bodega en la misma transacción."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.exceptions import ApiError
from apps.common.locks import lock_root_row
from apps.common.ownership import owner_filter

from ..exceptions import (
    BuyerInactive,
    SaleBuyerNotFound,
    SaleFarmInactive,
    SaleFarmNotFound,
    SaleLotInvalidStatus,
    SaleLotNotFound,
    SaleStockInsufficient,
)
from ..models import Sale, SaleAuditEvent, SaleCodeSequence, SaleLine
from ..rules import line_subtotal
from .queries import get_sale

# Los modelos de las otras apps se toman de las relaciones: ninguna app importa de otra.
Farm = Sale._meta.get_field("farm").related_model
Buyer = Sale._meta.get_field("buyer").related_model
Producer = Sale._meta.get_field("producer").related_model
Lot = SaleLine._meta.get_field("lot").related_model
StockExit = SaleLine._meta.get_field("stock_exit").related_model

IN_WAREHOUSE = "in_warehouse"
CREATED_FIELDS = ("farm", "buyer", "sale_date", "notes", "lines")


@transaction.atomic
def create_sale(actor, data: dict) -> Sale:
    """Registra la venta de los lotes de una finca a un comprador. Todo o nada: si una línea pide
    más de lo que hay, no queda ninguna salida, ninguna venta ni ningún número consumido."""
    farm = _locked_farm(actor, data["farm_id"])
    buyer = _active_buyer(farm, data["buyer_id"])
    lots = [_lot_to_sell(farm, line["lot_id"], index) for index, line in enumerate(data["lines"])]
    _check_date(data["sale_date"], lots)

    exits = []
    for index, (line, lot) in enumerate(zip(data["lines"], lots, strict=True)):
        try:
            exits.append(
                StockExit.remove_for_sale(
                    actor, lot, line["grade"], line["quantity_kg"], exit_date=data["sale_date"]
                )
            )
        except ApiError as error:
            # La bodega no dice qué línea pidió de más: se responde con su índice.
            if error.default_code != "stock_insufficient":
                raise
            raise SaleStockInsufficient(index, Decimal(error.extra["available_kg"])) from None

    sale = Sale.objects.create(
        producer_id=farm.producer_id,
        number=_next_number(farm.producer_id),
        farm=farm,
        buyer=buyer,
        sale_date=data["sale_date"],
        notes=data.get("notes", ""),
        created_by=actor,
        created_at=timezone.now(),
    )
    SaleLine.objects.bulk_create(
        SaleLine(
            sale=sale,
            lot=lot,
            grade=line["grade"],
            quantity_kg=line["quantity_kg"],
            price_per_kg=line["price_per_kg"],
            subtotal=line_subtotal(line["quantity_kg"], line["price_per_kg"]),
            stock_exit=stock_exit,
        )
        for line, lot, stock_exit in zip(data["lines"], lots, exits, strict=True)
    )
    SaleAuditEvent.record(
        sale=sale,
        actor=actor,
        action=SaleAuditEvent.Action.CREATED,
        changed_fields=CREATED_FIELDS,
        version=sale.version,
    )
    return get_sale(actor, sale.pk)


def _locked_farm(actor, farm_id):
    """La finca de la venta, bloqueada: toda escritura bajo una finca la bloquea, y así dos ventas
    que sacan del mismo lote se esperan."""
    if not Farm.objects.filter(pk=farm_id, **owner_filter(actor, farm="id")).exists():
        raise SaleFarmNotFound()
    farm = lock_root_row(Farm, farm_id)
    if farm is None:
        raise SaleFarmNotFound()
    if not farm.is_active:
        raise SaleFarmInactive()
    return farm


def _active_buyer(farm, buyer_id):
    buyer = Buyer.objects.filter(pk=buyer_id, producer_id=farm.producer_id).first()
    if buyer is None:
        raise SaleBuyerNotFound()
    if not buyer.is_active:
        raise BuyerInactive()
    return buyer


def _lot_to_sell(farm, lot_id, index):
    lot = (
        Lot.objects.select_related("stock_entry")
        .filter(pk=lot_id, harvest__plot__farm_id=farm.pk)
        .first()
    )
    if lot is None:
        raise SaleLotNotFound(index)
    if lot.status != IN_WAREHOUSE:
        raise SaleLotInvalidStatus(index, lot.status)
    return lot


def _check_date(sale_date, lots) -> None:
    for lot in lots:
        if sale_date < lot.stock_entry.entry_date:
            raise ValidationError(
                {"sale_date": [f"La fecha no puede ser anterior al ingreso del lote {lot.code}"]}
            )


def _next_number(producer_id) -> int:
    """El siguiente número de venta del productor. Se bloquea el productor y no la fila del
    contador, que puede no existir todavía: dos ventas de fincas distintas no toman el mismo."""
    lock_root_row(Producer, producer_id)
    sequence, _ = SaleCodeSequence.objects.get_or_create(producer_id=producer_id)
    sequence.last_value += 1
    sequence.save(update_fields=["last_value"])
    return sequence.last_value
