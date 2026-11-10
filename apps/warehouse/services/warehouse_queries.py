from django.db.models import QuerySet

from apps.common.ownership import owner_filter
from apps.common.text import normalize_catalog_name

from ..exceptions import WarehouseNotFound
from ..models import Warehouse
from ..usage import used_expression


def readable_warehouses(actor) -> QuerySet[Warehouse]:
    """Las bodegas que `actor` alcanza: el Productor, las de todas sus fincas; un empleado, las de
    las fincas en las que trabaja."""
    return (
        Warehouse.objects.filter(**owner_filter(actor, "farm__producer_id", farm="farm_id"))
        .select_related("farm")
        .annotate(in_use=used_expression())
    )


def list_warehouses(actor, filters: dict) -> QuerySet[Warehouse]:
    """Las bodegas con los filtros de la pantalla, por finca y nombre. `producer` solo lo usa la
    cuenta técnica, que sin él ve las de todos."""
    warehouses = readable_warehouses(actor)
    if "farm" in filters:
        warehouses = warehouses.filter(farm_id=filters["farm"])
    if "active" in filters:
        warehouses = warehouses.filter(is_active=filters["active"])
    if term := normalize_catalog_name(filters.get("search") or ""):
        warehouses = warehouses.filter(name_normalized__contains=term)
    if actor.is_superuser and "producer" in filters:
        warehouses = warehouses.filter(farm__producer_id=filters["producer"])
    return warehouses.order_by("farm__number", "name_normalized", "id")


def get_warehouse(actor, warehouse_id) -> Warehouse:
    try:
        return readable_warehouses(actor).get(pk=warehouse_id)
    except Warehouse.DoesNotExist:
        raise WarehouseNotFound() from None
