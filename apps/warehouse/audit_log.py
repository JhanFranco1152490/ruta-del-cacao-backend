"""Las existencias y las bodegas en la bitácora de cambios."""

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    KIND_DATE,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
    names_by_id,
    referenced_ids,
)

from .choices import ExitReason, Grade
from .models import StockAuditEvent, Warehouse, WarehouseAuditEvent

STOCK_LABELS = {
    "entry_date": "Fecha de ingreso",
    "warehouse_id": "Bodega",
    "location": "Ubicación",
    "g1_kg": "G1 (kg)",
    "g2_kg": "G2 (kg)",
    "grade": "Calibre",
    "quantity_kg": "Cantidad (kg)",
    "exit_date": "Fecha de la salida",
    "reason": "Motivo",
    "detail": "Detalle",
    "void_reason": "Motivo de la anulación",
}
STOCK_KINDS = {
    "entry_date": KIND_DATE,
    "exit_date": KIND_DATE,
    "g1_kg": KIND_NUMBER,
    "g2_kg": KIND_NUMBER,
    "quantity_kg": KIND_NUMBER,
}
# El id de la salida es interno: dice cuál se anuló, pero no es algo que se lea.
STOCK_SKIP = ("exit_id",)
WAREHOUSE_LABELS = {"name": "Nombre", "is_active": "Activa"}
WAREHOUSE_KINDS = {"is_active": KIND_BOOL}


def stock_events(producer_id, **filters):
    return audit_events(StockAuditEvent.objects.all(), producer_id, **filters)


def describe_stock(ids):
    found = list(StockAuditEvent.objects.filter(pk__in=ids).select_related("actor", "lot"))
    names = {
        "warehouse_id": names_by_id(
            Warehouse, referenced_ids(found, "warehouse_id"), lambda warehouse: warehouse.name
        ),
        "grade": dict(Grade.choices),
        "reason": dict(ExitReason.choices),
    }
    return [
        audit_entry(
            event,
            "stock",
            record_id=event.lot_id,
            record_label=event.lot.code,
            # Un lote que pasó por bodega no se elimina.
            record_deleted=False,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=STOCK_LABELS,
                kinds=STOCK_KINDS,
                names=names,
                skip=STOCK_SKIP,
            ),
        )
        for event in found
    ]


def warehouse_events(producer_id, **filters):
    return audit_events(WarehouseAuditEvent.objects.all(), producer_id, **filters)


def describe_warehouses(ids):
    found = WarehouseAuditEvent.objects.filter(pk__in=ids).select_related("actor")
    return [
        audit_entry(
            event,
            "warehouse",
            record_id=event.warehouse_ref,
            # El nombre de la copia: sirve también si la bodega ya se eliminó.
            record_label=event.warehouse_name,
            record_deleted=event.warehouse_id is None,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=WAREHOUSE_LABELS,
                kinds=WAREHOUSE_KINDS,
            ),
        )
        for event in found
    ]


STOCK_SOURCE = AuditSource(events=stock_events, describe=describe_stock)
WAREHOUSE_SOURCE = AuditSource(events=warehouse_events, describe=describe_warehouses)
