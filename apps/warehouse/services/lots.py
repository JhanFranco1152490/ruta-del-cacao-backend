"""Qué lotes de bodega alcanza quien actúa.

Todo el alcance de los lotes pasa por aquí: el productor alcanza lo de todas sus fincas, un
empleado lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import StockLotNotFound
from ..models import StockEntry

# El modelo del lote se toma de la relación y no de su app: ninguna app importa de otra.
Lot = StockEntry._meta.get_field("lot").related_model

# Los estados del lote que esta app usa, tal como los guarda su campo.
CLASSIFIED = "classified"
IN_WAREHOUSE = "in_warehouse"
STOCK_STATUSES = (CLASSIFIED, IN_WAREHOUSE)

LOT_SCOPE = {"field": "harvest__plot__farm__producer_id", "farm": "harvest__plot__farm_id"}


def lot_scope(actor) -> dict:
    return owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"])


def lock_lot(actor, lot_id):
    """El lote, en cualquier estado, con la finca de su parcela bloqueada hasta el final de la
    transacción. Quien llama decide si el estado le sirve: uno que no lo es responde su estado, no
    404."""
    lock_aggregate_root(
        Lot,
        lot_id,
        root="harvest__plot__farm",
        scope=lot_scope(actor),
        not_found=StockLotNotFound,
    )
    return Lot.objects.select_related("harvest__plot__farm", "classification", "stock_entry").get(
        pk=lot_id
    )
