from apps.common.producer_dependents import ProducerDependent

from .models import Farm
from .services.farms import has_business_records, remove_unimportant_farm


def _farms_of(producer):
    return Farm.objects.filter(producer_id=producer.pk).order_by("name_normalized", "id")


def _important_record(producer) -> str | None:
    # La misma regla que eliminar una finca por separado: cualquier tabla que la apunte, salvo
    # su auditoría, la vuelve importante.
    for farm in _farms_of(producer):
        if has_business_records(farm):
            return f"La finca «{farm.name}» tiene registros asociados."
    return None


def _delete_all(producer, actor) -> None:
    for farm in _farms_of(producer).select_for_update():
        remove_unimportant_farm(farm, actor)


farms_dependent = ProducerDependent(
    name="farms",
    important_record=_important_record,
    count=lambda producer: _farms_of(producer).count(),
    delete_all=_delete_all,
)
