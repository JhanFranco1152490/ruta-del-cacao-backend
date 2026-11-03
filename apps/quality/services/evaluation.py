"""Registrar la evaluación física de un lote Seco y corregirla mientras el lote siga Evaluado."""

from django.db import transaction
from django.utils import timezone

from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import LotInvalidStatus, StaleQualityVersion
from ..models import QualityAuditEvent, QualityEvaluation
from ..rules import check_percentages_total
from .audit import EVALUATION_FIELDS, evaluation_values, record_quality_event
from .queries import DRIED, EVALUATED, lock_lot


@transaction.atomic
def record_evaluation(actor, lot_id, data: dict) -> QualityEvaluation:
    """Guarda la evaluación y deja el lote Evaluado, en una sola transacción."""
    lot = lock_lot(actor, lot_id)
    # El estado va antes que la versión: si otra persona lo evaluó, eso es lo que hay que decir.
    if lot.status != DRIED:
        raise LotInvalidStatus(lot.status)
    if lot.version != data["expected_lot_version"]:
        raise StaleQualityVersion(lot.pk)
    values = {field: data.get(field, "") for field in EVALUATION_FIELDS}
    check_percentages_total(
        values["well_fermented_pct"], values["moldy_pct"], values["other_defects_pct"]
    )
    evaluation = QualityEvaluation.objects.create(
        lot=lot, **values, evaluated_by=actor, evaluated_at=timezone.now()
    )
    lot.advance_status(DRIED, EVALUATED, actor=actor)
    record_quality_event(
        lot=lot,
        actor=actor,
        action=QualityAuditEvent.Action.EVALUATED,
        before={},
        after=values,
        version=evaluation.version,
    )
    return evaluation


@transaction.atomic
def correct_evaluation(actor, lot_id, expected_version: int, changes: dict) -> QualityEvaluation:
    """Cambia los porcentajes o las observaciones y guarda quién corrigió y cuándo. Sin cambios
    reales, la versión no sube y no queda evento."""
    lot = lock_lot(actor, lot_id)
    if lot.status != EVALUATED:
        raise LotInvalidStatus(lot.status)
    evaluation = lot.quality_evaluation
    check_expected_version(evaluation, expected_version, stale=lambda: StaleQualityVersion(lot.pk))
    before = evaluation_values(evaluation)
    for field in EVALUATION_FIELDS:
        if field in changes:
            setattr(evaluation, field, changes[field])
    after = evaluation_values(evaluation)
    changed = [field for field in EVALUATION_FIELDS if after[field] != before[field]]
    if not changed:
        return evaluation
    check_percentages_total(
        evaluation.well_fermented_pct, evaluation.moldy_pct, evaluation.other_defects_pct
    )
    evaluation.corrected_by = actor
    evaluation.corrected_at = timezone.now()
    save_next_version(evaluation, [*changed, "corrected_by", "corrected_at"])
    record_quality_event(
        lot=lot,
        actor=actor,
        action=QualityAuditEvent.Action.EVALUATION_CORRECTED,
        before=before,
        after=after,
        version=evaluation.version,
    )
    return evaluation
