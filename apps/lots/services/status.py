from apps.common.versioning import save_next_version

from ..choices import allowed_next
from ..exceptions import LotInvalidStatus
from ..models import Lot, LotAuditEvent
from .audit import record_lot_event


def advance_lot_status(lot: Lot, expected: str, new: str, *, actor) -> Lot:
    """Mueve el lote de `expected` a `new`, que debe ser uno de los estados a los que puede pasar.

    Es el único punto por donde cambia el estado de un lote: fermentación, secado, calidad y lo que
    sigue la llaman dentro de su propia transacción, con el lote ya bloqueado (la finca de su
    parcela). Si el lote no está en `expected`, o no puede pasar de ahí a `new`, responde
    `LotInvalidStatus` con el estado actual y no cambia nada.
    """
    if lot.status != expected or new not in allowed_next(lot.status):
        raise LotInvalidStatus(lot.status)
    before = {"status": lot.status}
    lot.status = new
    save_next_version(lot, ["status"])
    record_lot_event(
        lot=lot,
        actor=actor,
        action=LotAuditEvent.Action.STATUS_CHANGED,
        before=before,
        after={"status": lot.status},
    )
    return lot
