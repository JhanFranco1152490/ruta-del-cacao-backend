"""Mover el cacao de un lote a otra bodega o ubicación de su finca."""

from django.db import transaction
from django.utils import timezone

from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import LotInvalidStatus, MoveUnchanged, NothingToMove, StaleStockVersion
from ..models import StockAuditEvent, StockBalance, StockMove
from .audit import record_stock_event
from .entry import usable_warehouse
from .lots import IN_WAREHOUSE, lock_lot


@transaction.atomic
def move_stock(actor, lot_id, expected_version: int, *, warehouse_id, location: str) -> StockMove:
    """Cambia la bodega y la ubicación donde está el cacao de un lote En bodega, y deja de dónde
    venía. A diferencia de corregir el ingreso, se puede hacer en cualquier momento: es un
    movimiento real, no la enmienda de un error. Las existencias no cambian."""
    lot = lock_lot(actor, lot_id)
    if lot.status != IN_WAREHOUSE:
        raise LotInvalidStatus(lot.status)
    entry = lot.stock_entry
    check_expected_version(entry, expected_version, stale=lambda: StaleStockVersion(lot.pk))
    balances = list(StockBalance.objects.select_for_update().filter(lot=lot))
    if not any(balance.quantity_kg > 0 for balance in balances):
        raise NothingToMove()
    warehouse = usable_warehouse(actor, lot, warehouse_id)
    if warehouse.pk == entry.warehouse_id and location == entry.location:
        raise MoveUnchanged()

    move = StockMove.objects.create(
        lot=lot,
        from_warehouse=entry.warehouse,
        from_location=entry.location,
        to_warehouse=warehouse,
        to_location=location,
        moved_by=actor,
        moved_at=timezone.now(),
    )
    before = {"warehouse_id": entry.warehouse_id, "location": entry.location}
    entry.warehouse, entry.location = warehouse, location
    save_next_version(entry, ["warehouse", "location"])
    for balance in balances:
        balance.warehouse, balance.location = warehouse, location
        balance.save(update_fields=["warehouse", "location", "updated_at"])
    record_stock_event(
        lot=lot,
        actor=actor,
        action=StockAuditEvent.Action.MOVED,
        before=before,
        after={"warehouse_id": warehouse.pk, "location": location},
        version=entry.version,
    )
    return move
