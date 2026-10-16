from apps.common.versioning import save_next_version

from ..choices import next_status
from ..exceptions import LotInvalidStatus
from ..models import Lot, LotAuditEvent
from .audit import record_lot_event


def advance_lot_status(lot: Lot, expected: str, new: str, *, actor) -> Lot:
    """Mueve el lote de `expected` a `new`, que debe ser el estado que sigue en la cadena.

    Es el único punto por donde cambia el estado de un lote: fermentación, secado y lo que sigue la
    llaman dentro de su propia transacción, con el lote ya bloqueado (la finca de su parcela). Si
    el lote no está en `expected`, o `new` no es el siguiente, responde `LotInvalidStatus` con el
    estado actual y no cambia nada.
    """
    if lot.status != expected or next_status(lot.status) != new:
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
