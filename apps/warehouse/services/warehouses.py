from functools import partial

from django.db import transaction
from django.db.models import ProtectedError

from apps.common.audit import record_update_events
from apps.common.db import save_translating_unique
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import (
    StaleWarehouseVersion,
    WarehouseHasRecords,
    WarehouseNameTaken,
    WarehouseNotFound,
)
from ..models import Warehouse, WarehouseAuditEvent
from ..usage import is_used
from .audit import record_warehouse_event
from .farms import ensure_farm_active, ensure_has_a_farm, lock_farm

NAME_UNIQUE_CONSTRAINT = "warehouse_warehouse_farm_name_unique"
CONTENT_FIELDS = ("name", "is_active")


def _duplicate_error(warehouse: Warehouse) -> WarehouseNameTaken:
    existing = (
        Warehouse.objects.filter(
            farm_id=warehouse.farm_id, name_normalized=warehouse.name_normalized
        )
        .exclude(pk=warehouse.pk)
        .first()
    )
    return WarehouseNameTaken(existing)


@transaction.atomic
def create_warehouse(actor, data: dict) -> Warehouse:
    """Registra una bodega en una finca que `actor` alcanza. Queda activa. Solo en línea: el
    servidor genera el `id`."""
    ensure_has_a_farm(actor)
    farm = lock_farm(actor, data["farm_id"])
    ensure_farm_active(farm)

    warehouse = Warehouse(farm=farm, name=data["name"], created_by=actor)
    warehouse.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    save_translating_unique(
        lambda: warehouse.save(force_insert=True),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=lambda: _duplicate_error(warehouse),
    )
    record_warehouse_event(
        warehouse=warehouse,
        actor=actor,
        action=WarehouseAuditEvent.Action.CREATED,
        changed_fields=CONTENT_FIELDS,
    )
    warehouse.in_use = False
    return warehouse


def _lock_warehouse(actor, warehouse_id) -> Warehouse:
    warehouse, _farm = lock_aggregate_root(
        Warehouse,
        warehouse_id,
        root="farm",
        scope=owner_filter(actor, "farm__producer_id", farm="farm_id"),
        not_found=WarehouseNotFound,
    )
    return warehouse


@transaction.atomic
def update_warehouse(actor, warehouse_id, expected_version: int, data: dict) -> Warehouse:
    """Cambia el nombre o activa y desactiva una bodega. La finca no se edita. Sin cambios reales
    devuelve la bodega tal cual, sin subir la versión ni dejar historial."""
    warehouse = _lock_warehouse(actor, warehouse_id)
    check_expected_version(
        warehouse, expected_version, stale=lambda: StaleWarehouseVersion(_with_usage(warehouse))
    )

    before = {name: getattr(warehouse, name) for name in CONTENT_FIELDS}
    for name, value in data.items():
        setattr(warehouse, name, value)
    warehouse.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    # Se compara después de validar: un nombre que solo cambió en espacios no es un cambio.
    changed = [name for name in CONTENT_FIELDS if getattr(warehouse, name) != before[name]]
    if not changed:
        return _with_usage(warehouse)

    save_next_version(
        warehouse,
        [*changed, "name_normalized"] if "name" in changed else changed,
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=lambda: _duplicate_error(warehouse),
    )
    record_update_events(
        partial(record_warehouse_event, warehouse=warehouse, actor=actor, before=before),
        changed,
        updated=WarehouseAuditEvent.Action.UPDATED,
        status_changed=WarehouseAuditEvent.Action.STATUS_CHANGED,
    )
    return _with_usage(warehouse)


@transaction.atomic
def delete_warehouse(actor, warehouse_id, expected_version: int) -> None:
    """Elimina una bodega registrada por error. Solo si nunca recibió un ingreso; la que se usó se
    desactiva. Su historial se conserva y el borrado queda registrado en él."""
    warehouse = _lock_warehouse(actor, warehouse_id)
    check_expected_version(
        warehouse, expected_version, stale=lambda: StaleWarehouseVersion(_with_usage(warehouse))
    )
    remove_warehouse(warehouse, actor)


def remove_warehouse(warehouse: Warehouse, actor) -> None:
    """Elimina `warehouse` y deja el rastro. Quien llama ya validó quién puede hacerlo: aquí solo
    se aplica la regla. Si algo la usa, `WarehouseHasRecords` y no se toca nada."""
    if is_used(warehouse):
        raise WarehouseHasRecords()
    record_warehouse_event(
        warehouse=warehouse, actor=actor, action=WarehouseAuditEvent.Action.DELETED
    )
    try:
        warehouse.delete()
    except ProtectedError:
        # Un registro que apunta a la bodega apareció entre la revisión y el borrado: la base es la
        # garantía final. La transacción de quien llama deshace también el evento.
        raise WarehouseHasRecords() from None


def _with_usage(warehouse: Warehouse) -> Warehouse:
    warehouse.in_use = is_used(warehouse)
    return warehouse
