"""La historia de un lote: sus etapas, de la cosecha a lo último que pasó, y su estado actual.

Cada app del proceso aporta sus etapas por el contrato de la historia; aquí se juntan con las del
propio lote y se ordenan. Nada se guarda: la historia se arma con los registros al pedirla.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.common.contracts.lot_history import LotHistoryStage, lot_history_source

from ..history import created_stage, harvest_stage
from ..history_order import order_stages
from ..models import Lot
from .queries import get_lot

# Las fuentes de etapas de las apps del proceso, en el orden del proceso.
STAGE_SOURCES = (
    "fermentation_history",
    "drying_history",
    "quality_history",
    "warehouse_history",
    "sales_history",
)


@dataclass(frozen=True)
class LotCurrent:
    status: str
    # Nulos mientras el lote no haya ingresado a bodega.
    g1_available_kg: Decimal | None
    g2_available_kg: Decimal | None
    sold_kg: Decimal | None


@dataclass(frozen=True)
class LotHistory:
    lot: Lot
    stages: list[LotHistoryStage]
    current: LotCurrent


def _current(lot) -> LotCurrent:
    stock = lot_history_source("stock_now")(lot.pk)
    if stock is None:
        return LotCurrent(lot.status, None, None, None)
    sold = lot_history_source("sold_now")(lot.pk)
    return LotCurrent(lot.status, stock.g1_available_kg, stock.g2_available_kg, sold.sold_kg)


def lot_history(actor, lot_id) -> LotHistory:
    """La historia del lote, si `actor` lo alcanza; si no, el mismo `404` de uno que no existe."""
    lot = get_lot(actor, lot_id, details=False)
    stages = [harvest_stage(lot), created_stage(lot)]
    for name in STAGE_SOURCES:
        stages.extend(lot_history_source(name)(lot.pk))
    return LotHistory(lot=lot, stages=order_stages(stages), current=_current(lot))
