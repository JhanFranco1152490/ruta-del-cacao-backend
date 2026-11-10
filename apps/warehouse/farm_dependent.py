from apps.common.contracts.farm_dependents import FarmDependent

from .models import Warehouse
from .services.warehouses import remove_warehouse
from .usage import is_used


def _warehouses_of(farm):
    return Warehouse.objects.filter(farm_id=farm.pk).order_by("name_normalized", "id")


def _important_record(farm) -> str | None:
    # La misma regla que eliminar una bodega por separado: si recibió un lote, la finca no se
    # elimina, se desactiva.
    for warehouse in _warehouses_of(farm):
        if is_used(warehouse):
            return f"La bodega «{warehouse.name}» ya recibió ingresos."
    return None


def _delete_all(farm, actor) -> None:
    for warehouse in _warehouses_of(farm):
        remove_warehouse(warehouse, actor)


warehouses_dependent = FarmDependent(
    name="warehouses",
    important_record=_important_record,
    count=lambda farm: _warehouses_of(farm).count(),
    delete_all=_delete_all,
    models=(Warehouse,),
)
