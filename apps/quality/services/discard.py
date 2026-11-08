"""Descartar un lote Evaluado completo y avisar a quienes trabajan la calidad en su finca."""

from django.db import transaction
from django.utils import timezone

from apps.common.contracts.alerts import NotificationDraft, notify
from apps.common.contracts.schedulers import FarmAccounts

from ..exceptions import LotInvalidStatus, StaleQualityVersion
from ..models import LotDiscard, QualityAuditEvent
from .audit import record_quality_event
from .queries import DISCARDED, EVALUATED, lock_lot

DISCARD_FIELDS = ("reason", "detail")
# Quien lo tiene trabaja la calidad del lote: a esas cuentas les llega el aviso, por el permiso y
# no por el nombre del rol, que en un rol propio puede ser cualquiera. El Productor lo tiene.
QUALITY_PERMISSION = "quality.evaluate_lot"
# El tipo de aviso, como lo guarda la app de notificaciones, que esta no importa.
LOT_DISCARDED = "lot_discarded"


@transaction.atomic
def discard_lot(actor, lot_id, data: dict) -> LotDiscard:
    """Guarda el descarte, deja el lote Descartado y pide los avisos, en una sola transacción: si
    algo falla, no queda nada y no sale ningún aviso."""
    lot = lock_lot(actor, lot_id)
    if lot.status != EVALUATED:
        raise LotInvalidStatus(lot.status)
    if lot.version != data["expected_lot_version"]:
        raise StaleQualityVersion(lot.pk)
    values = {field: data.get(field, "") for field in DISCARD_FIELDS}
    discard = LotDiscard.objects.create(
        lot=lot, **values, discarded_by=actor, discarded_at=timezone.now()
    )
    lot.advance_status(EVALUATED, DISCARDED, actor=actor)
    record_quality_event(
        lot=lot,
        actor=actor,
        action=QualityAuditEvent.Action.DISCARDED,
        before={},
        after=values,
        version=lot.quality_evaluation.version,
    )
    notify(discard_notices(lot, discard, actor))
    return discard


def discard_notices(lot, discard, actor) -> list[NotificationDraft]:
    """Un aviso por cada cuenta activa que trabaja la calidad en la finca del lote, menos quien
    descartó: ya lo sabe."""
    farm = lot.harvest.plot.farm
    recipients = FarmAccounts({farm.producer_id}, QUALITY_PERMISSION).on_farm(
        farm.producer_id, farm.pk
    )
    recipients.discard(actor.pk)
    return [
        NotificationDraft(
            recipient_id=recipient_id,
            kind=LOT_DISCARDED,
            condition_key=f"{lot.pk}:discarded",
            thread_key=f"lot:{lot.pk}:quality",
            lot_id=lot.pk,
            condition_at=discard.discarded_at,
        )
        for recipient_id in sorted(recipients, key=str)
    ]
