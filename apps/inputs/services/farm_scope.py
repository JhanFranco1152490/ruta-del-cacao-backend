"""Lo que un empleado puede hacer con los insumos de las fincas en las que trabaja.

El catálogo es uno por productor. Un empleado ve y toca solo los insumos de sus fincas: los que
tienen una fila de existencias en alguna de ellas. El Productor y la cuenta técnica no pasan por
estas reglas.
"""

from decimal import Decimal

from rest_framework.exceptions import ValidationError

from apps.common.ownership import owner_filter, reaches_all_farms

from ..exceptions import FarmRequired, InputNotFound, InputShared, UnitChangeNotAllowed
from ..models import AgriculturalInput, InputStock

CHOOSE_A_FARM = "Indica en cuál de tus fincas queda el insumo."
FARM_NOT_AVAILABLE = "Elige una finca del productor."


def farm_for_new_input(actor, producer_id, farm_id):
    """La finca en la que queda un insumo recién registrado, o `None` si no queda en ninguna.

    Un empleado lo deja siempre en una de sus fincas: así lo ve desde ya, antes de registrarle la
    primera entrada. Si trabaja en una sola no hace falta decir cuál; si trabaja en varias, sí.
    El Productor puede indicar una finca o ninguna (queda solo en el catálogo).
    """
    if farm_id is None:
        if reaches_all_farms(actor):
            return None
        own = list(actor.farms.all()[:2])
        if not own:
            raise FarmRequired()
        if len(own) > 1:
            raise ValidationError({"farm_id": [CHOOSE_A_FARM]})
        return own[0]
    farm_model = InputStock._meta.get_field("farm").related_model
    farm = (
        farm_model.objects.filter(pk=farm_id, producer_id=producer_id)
        .filter(**owner_filter(actor, farm="id"))
        .first()
    )
    if farm is None:
        raise ValidationError({"farm_id": [FARM_NOT_AVAILABLE]})
    return farm


def place_in_farm(item: AgriculturalInput, farm) -> None:
    """Marca que el insumo está en la finca, con existencias en cero."""
    if farm is not None:
        InputStock.objects.create(input=item, farm=farm, quantity=Decimal("0"))


def ensure_has_a_farm(actor) -> None:
    if not reaches_all_farms(actor) and not actor.farms.exists():
        raise FarmRequired()


def ensure_can_change(actor, item: AgriculturalInput, changed=()) -> None:
    """Un empleado edita, desactiva o elimina solo un insumo que está nada más en una finca, y que
    sea suya; nunca le cambia la unidad. `item` ya está bloqueado por quien llama."""
    if reaches_all_farms(actor):
        return
    farms = set(item.stocks.values_list("farm_id", flat=True))
    if not farms & {farm.pk for farm in actor.farms.all()}:
        # De otra finca: como si no existiera.
        raise InputNotFound()
    if len(farms) > 1:
        raise InputShared()
    if "unit" in changed:
        raise UnitChangeNotAllowed()
