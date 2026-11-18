"""Las existencias de hoy en los reportes del productor: sin periodo, como en bodega."""

from django.db.models import Sum

from apps.common.contracts.reports import LotStock, PlotPlace, StockRow
from apps.common.figures import ZERO

from .models import StockBalance, StockEntry

FARM = "warehouse__farm_id"


def stock_rows(farm_ids, *, plot_id=None, lot_id=None) -> list[StockRow]:
    balances = StockBalance.objects.filter(
        **{f"{FARM}__in": farm_ids}, quantity_kg__gt=0
    ).select_related("lot__harvest__plot__farm", "lot__stock_entry", "warehouse")
    if plot_id is not None:
        balances = balances.filter(lot__harvest__plot_id=plot_id)
    if lot_id is not None:
        balances = balances.filter(lot_id=lot_id)
    return [
        StockRow(
            lot_id=balance.lot_id,
            lot_code=balance.lot.code,
            place=PlotPlace.of(balance.lot.harvest.plot),
            warehouse=balance.warehouse.name,
            location=balance.location,
            grade=balance.get_grade_display(),
            kg=balance.quantity_kg,
            entry_date=balance.lot.stock_entry.entry_date,
        )
        for balance in balances
    ]


def stock_by_lot(lot_ids) -> list[LotStock]:
    """Cuándo entró cada uno de esos lotes a bodega y cuánto le queda hoy (0 si ya salió todo)."""
    if not lot_ids:
        return []
    entries = (
        StockEntry.objects.filter(lot_id__in=lot_ids)
        .annotate(available_kg=Sum("lot__stock_balances__quantity_kg"))
        .values("lot_id", "entry_date", "available_kg")
    )
    return [
        LotStock(
            lot_id=row["lot_id"],
            entry_date=row["entry_date"],
            available_kg=row["available_kg"] or ZERO,
        )
        for row in entries
    ]
