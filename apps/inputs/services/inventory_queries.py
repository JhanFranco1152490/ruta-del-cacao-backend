from django.db.models import QuerySet

from apps.common.ownership import owner_filter

from ..exceptions import FarmNotFound, InputNotFound
from ..models import AgriculturalInput, InputMovement, InputStock


def list_stocks(actor, farm_id) -> QuerySet[InputStock]:
    """Las existencias de una finca, solo de los insumos con movimientos. Una finca ajena o que no
    existe da la lista vacía, como las parcelas de una finca ajena."""
    return InputStock.objects.filter(
        farm_id=farm_id, **owner_filter(actor, "input__producer_id")
    ).order_by("input__name_normalized", "input_id")


def list_movements(actor, input_id, farm_id) -> QuerySet[InputMovement]:
    """Los movimientos de un insumo en una finca, del más nuevo al más viejo. Un insumo o una finca
    ajenos o inexistentes son `404`."""
    if not AgriculturalInput.objects.filter(pk=input_id, **owner_filter(actor)).exists():
        raise InputNotFound()
    farm_model = InputMovement._meta.get_field("farm").related_model
    if not farm_model.objects.filter(pk=farm_id, **owner_filter(actor)).exists():
        raise FarmNotFound()
    return InputMovement.objects.filter(input_id=input_id, farm_id=farm_id).select_related("actor")
