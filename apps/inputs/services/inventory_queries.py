from django.db.models import Exists, OuterRef, QuerySet

from apps.common.ownership import owner_filter

from ..exceptions import FarmNotFound, InputNotFound
from ..models import AgriculturalInput, InputMovement, InputStock


def list_stocks(actor, farm_id=None, producer=None) -> QuerySet[InputStock]:
    """Las existencias de los insumos con movimientos: las de una finca (`farm_id`) o, sin ella,
    las de todas las fincas del alcance de quien llama, una fila por insumo y finca. Una finca
    ajena o que no existe da la lista vacía, como las parcelas de una finca ajena. Solo la cuenta
    técnica elige de qué productor ver (`producer`); para las demás el alcance ya es el suyo. Un
    empleado solo recibe las de la finca en la que trabaja.

    Un insumo recién registrado en una finca ya tiene su fila de existencias, en cero y sin
    movimientos: no se lista, para que siga viéndose «Sin movimientos» y no «0»."""
    has_movements = InputMovement.objects.filter(
        input_id=OuterRef("input_id"), farm_id=OuterRef("farm_id")
    )
    stocks = InputStock.objects.filter(
        Exists(has_movements), **owner_filter(actor, "input__producer_id", farm="farm_id")
    )
    if farm_id is not None:
        stocks = stocks.filter(farm_id=farm_id)
    if producer is not None and actor.is_superuser:
        stocks = stocks.filter(input__producer_id=producer)
    return stocks.order_by("input__name_normalized", "input_id", "farm_id")


def list_movements(actor, input_id, farm_id) -> QuerySet[InputMovement]:
    """Los movimientos de un insumo en una finca, del más nuevo al más viejo. Un insumo o una finca
    ajenos o inexistentes son `404`, y para un empleado también los de otra finca."""
    if not AgriculturalInput.objects.filter(pk=input_id, **owner_filter(actor)).exists():
        raise InputNotFound()
    farm_model = InputMovement._meta.get_field("farm").related_model
    if not farm_model.objects.filter(pk=farm_id, **owner_filter(actor, farm="id")).exists():
        raise FarmNotFound()
    return InputMovement.objects.filter(input_id=input_id, farm_id=farm_id).select_related("actor")
