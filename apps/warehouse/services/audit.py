from apps.common.audit import field_changes

from ..models import ONE_DECIMAL, StockAuditEvent, Warehouse, WarehouseAuditEvent

# Lo que describe un ingreso, con los valores que entrega la API.
ENTRY_FIELDS = ("entry_date", "warehouse_id", "location", "g1_kg", "g2_kg")


def record_warehouse_event(
    *, warehouse: Warehouse, actor, action: str, changed_fields=(), before: dict | None = None
) -> WarehouseAuditEvent:
    """Deja un evento con, por cada campo cambiado, su valor anterior y nuevo. Sin `before` (el
    alta y el borrado), cada anterior es `None`."""
    fields = sorted(set(changed_fields))
    changes = field_changes(
        before or {}, {name: getattr(warehouse, name) for name in fields}, fields=fields
    )
    return WarehouseAuditEvent.record(
        warehouse=warehouse,
        warehouse_ref=warehouse.pk,
        warehouse_name=warehouse.name,
        farm_ref=warehouse.farm_id,
        actor=actor,
        action=action,
        changed_fields=fields,
        version=warehouse.version,
        changes=changes,
    )


def entry_values(entry) -> dict:
    return {field: getattr(entry, field) for field in ENTRY_FIELDS}


def record_stock_event(
    *, lot, actor, action: str, before: dict, after: dict, version: int
) -> StockAuditEvent:
    changes = field_changes(before, after, decimal_places=ONE_DECIMAL)
    return StockAuditEvent.record(
        lot=lot,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=version,
        changes=changes,
    )
