"""Qué lotes y cosechas alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un
empleado lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from django.db.models import QuerySet

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import HarvestNotFound, LotNotFound
from ..models import Lot

# El modelo de la cosecha se toma de la relación y no de su app: ninguna app importa de otra.
Harvest = Lot._meta.get_field("harvest").related_model

LOT_SCOPE = {"field": "harvest__plot__farm__producer_id", "farm": "harvest__plot__farm_id"}


def visible_lots(actor) -> QuerySet[Lot]:
    return Lot.objects.filter(
        **owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"])
    ).select_related(
        "harvest__plot__farm__producer",
        "harvest__variety",
        "harvest__collector",
        "harvest__registered_by",
        "created_by",
    )


def get_lot(actor, lot_id) -> Lot:
    lot = visible_lots(actor).filter(pk=lot_id).first()
    if lot is None:
        raise LotNotFound()
    return lot


def lock_harvest(actor, harvest_id):
    """La cosecha, con la finca de su parcela bloqueada hasta el final de la transacción, y con
    lo que el código del lote necesita (parcela, finca y productor) ya cargado."""
    harvest, _ = lock_aggregate_root(
        Harvest,
        harvest_id,
        root="plot__farm",
        scope=owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id"),
        not_found=HarvestNotFound,
    )
    return Harvest.objects.select_related("plot__farm__producer").get(pk=harvest.pk)
