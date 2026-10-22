from apps.common.contracts.farm_dependents import FarmDependent

from .models import InputStock


def _stocks_of(farm):
    return InputStock.objects.filter(farm_id=farm.pk)


def _delete_all(farm, actor) -> None:
    _stocks_of(farm).delete()


# Las existencias de una finca solo dicen qué insumos están en ella: no impiden eliminarla y se
# van con ella. Lo que sí la vuelve importante son los movimientos, que apuntan a la finca por su
# cuenta y la bloquean sin pasar por aquí.
inputs_dependent = FarmDependent(
    name="inputs",
    important_record=lambda farm: None,
    count=lambda farm: _stocks_of(farm).count(),
    delete_all=_delete_all,
    models=(InputStock,),
)
