"""Clasificar un lote Evaluado: repartir su peso seco entre G1, G2 y descarte."""

from django.db import transaction
from django.utils import timezone

from ..exceptions import LotInvalidStatus, StaleQualityVersion
from ..models import LotClassification, QualityAuditEvent
from ..rules import check_classification_total
from .audit import record_quality_event
from .queries import CLASSIFIED, EVALUATED, lock_lot

CLASSIFICATION_FIELDS = ("g1_kg", "g2_kg", "discard_kg", "discard_reason", "discard_detail")


@transaction.atomic
def classify_lot(actor, lot_id, data: dict) -> LotClassification:
    """Guarda la clasificación y deja el lote Clasificado, en una sola transacción. El peso seco
    se lee del secado del lote ya bloqueado: es el que vale, no el que vio el formulario."""
    lot = lock_lot(actor, lot_id)
    if lot.status != EVALUATED:
        raise LotInvalidStatus(lot.status)
    if lot.version != data["expected_lot_version"]:
        raise StaleQualityVersion(lot.pk)
    values = {field: data.get(field, "") for field in CLASSIFICATION_FIELDS}
    check_classification_total(
        lot.drying.dry_weight_kg, values["g1_kg"], values["g2_kg"], values["discard_kg"]
    )
    classification = LotClassification.objects.create(
        lot=lot, **values, classified_by=actor, classified_at=timezone.now()
    )
    lot.advance_status(EVALUATED, CLASSIFIED, actor=actor)
    record_quality_event(
        lot=lot,
        actor=actor,
        action=QualityAuditEvent.Action.CLASSIFIED,
        before={},
        after=values,
        version=lot.quality_evaluation.version,
    )
    return classification
