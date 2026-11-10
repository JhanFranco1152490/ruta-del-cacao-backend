"""Ingresar a bodega un lote Clasificado y corregir ese ingreso."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version, save_next_version

from ..choices import Grade
from ..exceptions import (
    EntryHasMovements,
    LotInvalidStatus,
    LotNothingToStore,
    StaleStockVersion,
    WarehouseFarmMismatch,
    WarehouseInactive,
    WarehouseNotFound,
)
from ..models import StockAuditEvent, StockBalance, StockEntry, Warehouse
from ..rules import entry_date_errors, entry_is_intact
from .audit import ENTRY_FIELDS, entry_values, record_stock_event
from .lots import CLASSIFIED, IN_WAREHOUSE, lock_lot


def usable_warehouse(actor, lot, warehouse_id) -> Warehouse:
    """La bodega elegida para un ingreso: de las que `actor` alcanza, de la finca del lote y
    activa."""
    warehouse = (
        Warehouse.objects.filter(
            pk=warehouse_id, **owner_filter(actor, "farm__producer_id", farm="farm_id")
        )
        .select_related("farm")
        .first()
    )
    if warehouse is None:
        raise WarehouseNotFound()
    # El cacao se guarda en la finca donde se cosechó.
    if warehouse.farm_id != lot.harvest.plot.farm_id:
        raise WarehouseFarmMismatch()
    if not warehouse.is_active:
        raise WarehouseInactive()
    return warehouse


def check_entry_date(entry_date, lot) -> None:
    classified_on = timezone.localtime(lot.classification.classified_at).date()
    errors = entry_date_errors(entry_date, today=timezone.localdate(), classified_on=classified_on)
    if errors:
        raise ValidationError({"entry_date": errors})


@transaction.atomic
def register_entry(actor, lot_id, data: dict) -> StockEntry:
    """Ingresa el lote a una bodega con los kilos de G1 y de G2 que dejó su clasificación y lo
    deja En bodega, en una sola transacción."""
    lot = lock_lot(actor, lot_id)
    # El estado va antes que la versión: si otra persona lo ingresó, eso es lo que hay que decir.
    if lot.status != CLASSIFIED:
        raise LotInvalidStatus(lot.status)
    if lot.version != data["expected_lot_version"]:
        raise StaleStockVersion(lot.pk)
    g1_kg, g2_kg = lot.classification.g1_kg, lot.classification.g2_kg
    if g1_kg + g2_kg <= 0:
        raise LotNothingToStore()
    warehouse = usable_warehouse(actor, lot, data["warehouse_id"])
    check_entry_date(data["entry_date"], lot)

    entry = StockEntry.objects.create(
        lot=lot,
        warehouse=warehouse,
        location=data["location"],
        entry_date=data["entry_date"],
        g1_kg=g1_kg,
        g2_kg=g2_kg,
        entered_by=actor,
        entered_at=timezone.now(),
    )
    StockBalance.objects.bulk_create(
        StockBalance(
            lot=lot,
            grade=grade,
            quantity_kg=kilos,
            warehouse=warehouse,
            location=entry.location,
        )
        for grade, kilos in ((Grade.G1, g1_kg), (Grade.G2, g2_kg))
        if kilos > 0
    )
    lot.advance_status(CLASSIFIED, IN_WAREHOUSE, actor=actor)
    record_stock_event(
        lot=lot,
        actor=actor,
        action=StockAuditEvent.Action.ENTERED,
        before={},
        after=entry_values(entry),
        version=entry.version,
    )
    return entry


@transaction.atomic
def correct_entry(actor, lot_id, expected_version: int, changes: dict) -> StockEntry:
    """Cambia la fecha, la bodega o la ubicación de un ingreso, y las existencias con él. Solo
    mientras no haya salido nada del lote: con una salida en vigor el ingreso ya tiene
    consecuencias. Sin cambios reales, la versión no sube y no queda evento."""
    lot = lock_lot(actor, lot_id)
    if lot.status != IN_WAREHOUSE:
        raise LotInvalidStatus(lot.status)
    entry = lot.stock_entry
    check_expected_version(entry, expected_version, stale=lambda: StaleStockVersion(lot.pk))
    balances = list(StockBalance.objects.select_for_update().filter(lot=lot))
    entered = {Grade.G1: entry.g1_kg, Grade.G2: entry.g2_kg}
    if not entry_is_intact(entered, {balance.grade: balance.quantity_kg for balance in balances}):
        raise EntryHasMovements()

    before = entry_values(entry)
    if "warehouse_id" in changes and changes["warehouse_id"] != entry.warehouse_id:
        entry.warehouse = usable_warehouse(actor, lot, changes["warehouse_id"])
    if "entry_date" in changes and changes["entry_date"] != entry.entry_date:
        check_entry_date(changes["entry_date"], lot)
        entry.entry_date = changes["entry_date"]
    if "location" in changes:
        entry.location = changes["location"]
    after = entry_values(entry)
    changed = [field for field in ENTRY_FIELDS if after[field] != before[field]]
    if not changed:
        return entry

    entry.corrected_by = actor
    entry.corrected_at = timezone.now()
    save_next_version(
        entry,
        [
            *(("warehouse" if field == "warehouse_id" else field) for field in changed),
            "corrected_by",
            "corrected_at",
        ],
    )
    for balance in balances:
        balance.warehouse, balance.location = entry.warehouse, entry.location
        balance.save(update_fields=["warehouse", "location", "updated_at"])
    record_stock_event(
        lot=lot,
        actor=actor,
        action=StockAuditEvent.Action.ENTRY_CORRECTED,
        before={field: before[field] for field in changed},
        after={field: after[field] for field in changed},
        version=entry.version,
    )
    return entry
