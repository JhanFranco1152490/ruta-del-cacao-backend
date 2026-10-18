from apps.common.farm_dependents import FarmDependent

from .models import PostharvestFacility
from .services.delete import remove_facility
from .usage import is_used


def _facilities_of(farm):
    return PostharvestFacility.objects.filter(farm_id=farm.pk).order_by("name_normalized", "id")


def _important_record(farm) -> str | None:
    # La misma regla que eliminar un elemento por separado: si un proceso lo usó, la finca no se
    # elimina, se desactiva.
    for facility in _facilities_of(farm):
        if facility.current_lot_id is not None:
            return f"El elemento «{facility.name}» tiene un lote adentro."
        if is_used(facility):
            return f"El elemento «{facility.name}» se usó en un proceso."
    return None


def _delete_all(farm, actor) -> None:
    for facility in _facilities_of(farm):
        remove_facility(facility, actor)


facilities_dependent = FarmDependent(
    name="facilities",
    important_record=_important_record,
    count=lambda farm: _facilities_of(farm).count(),
    delete_all=_delete_all,
    models=(PostharvestFacility,),
)
