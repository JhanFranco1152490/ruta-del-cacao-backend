from django.db import transaction

from apps.common.versioning import check_expected_version

from ..choices import LotStatus
from ..exceptions import LotInvalidStatus, StaleLotVersion
from ..models import LotAuditEvent
from . import queries
from .audit import record_lot_event


@transaction.atomic
def delete_lot(actor, lot_id, expected_version: int) -> None:
    """Elimina un lote conformado por error, mientras siga Generado: en cualquier otro estado ya
    tiene proceso registrado. La cosecha queda sin lote y vuelve a poder corregirse. El código no
    se vuelve a usar (el consecutivo de la parcela y el día no baja) y el historial conserva el
    código y la cosecha de origen."""
    lot = queries.lock_lot(actor, lot_id)
    if lot.status != LotStatus.GENERATED:
        raise LotInvalidStatus(lot.status)
    check_expected_version(lot, expected_version, stale=lambda: StaleLotVersion(lot))
    record_lot_event(lot=lot, actor=actor, action=LotAuditEvent.Action.DELETED)
    lot.delete()
