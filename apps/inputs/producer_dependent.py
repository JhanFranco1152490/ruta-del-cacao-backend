from apps.common.producer_dependents import ProducerDependent

from .models import AgriculturalInput
from .services import remove_input
from .usage import is_used


def _inputs_of(producer):
    return AgriculturalInput.objects.filter(producer_id=producer.pk).order_by(
        "name_normalized", "id"
    )


def _important_record(producer) -> str | None:
    # La misma regla que eliminar un insumo por separado: uno que algún registro usa es importante.
    for item in _inputs_of(producer):
        if is_used(item):
            return f"El insumo «{item.name}» tiene registros asociados."
    return None


def _delete_all(producer, actor) -> None:
    for item in _inputs_of(producer).select_for_update():
        remove_input(item, actor)


inputs_dependent = ProducerDependent(
    name="inputs",
    important_record=_important_record,
    count=lambda producer: _inputs_of(producer).count(),
    delete_all=_delete_all,
    models=(AgriculturalInput,),
)
