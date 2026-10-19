from apps.common.ownership import owner_filter, reaches_all_farms

from ..exceptions import FarmInactive, FarmNotFound, FarmRequired
from ..models import PostharvestFacility

# El modelo de la finca se toma de la relación y no de su app: ninguna app importa de otra.
Farm = PostharvestFacility._meta.get_field("farm").related_model


def lock_farm(actor, farm_id):
    """La finca, si `actor` la alcanza, bloqueada hasta el final de la transacción. Toda escritura
    sobre los cajones y marquesinas de una finca toma solo este bloqueo."""
    farm = Farm.objects.select_for_update().filter(pk=farm_id, **owner_filter(actor, farm="id"))
    farm = farm.first()
    if farm is None:
        raise FarmNotFound()
    return farm


def ensure_has_a_farm(actor) -> None:
    # Sin fincas un empleado no alcanza ninguna: se le dice eso en vez de que la finca no existe.
    if not reaches_all_farms(actor) and not actor.farms.exists():
        raise FarmRequired()


def ensure_farm_active(farm) -> None:
    if not farm.is_active:
        raise FarmInactive()
