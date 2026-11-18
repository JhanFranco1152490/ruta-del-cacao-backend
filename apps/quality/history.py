"""La calidad en la historia de un lote: la evaluación y, al cerrarla, la clasificación (con su
descarte parcial) o el descarte del lote completo."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from rest_framework import serializers

from apps.common.contracts.lot_history import LotHistoryStage
from apps.common.figures import quality_split
from apps.common.serializers import full_name

from .choices import DiscardReason
from .models import ONE_DECIMAL, QualityEvaluation


@dataclass(frozen=True)
class EvaluationData:
    evaluated_by: str
    well_fermented_pct: Decimal
    moldy_pct: Decimal
    other_defects_pct: Decimal
    # La evaluación tiene su valor vigente; esto dice si se corrigió y cuándo.
    corrected_at: datetime | None


@dataclass(frozen=True)
class ClassificationData:
    classified_by: str
    dry_weight_kg: Decimal
    g1_kg: Decimal
    g2_kg: Decimal
    discard_kg: Decimal
    g1_pct: Decimal | None
    g2_pct: Decimal | None
    discard_pct: Decimal | None
    # Sin descarte, sin motivo.
    discard_reason: str | None
    discard_detail: str


@dataclass(frozen=True)
class DiscardData:
    discarded_by: str
    # El descarte completo no guarda su peso: es todo el peso seco del lote.
    quantity_kg: Decimal
    reason: str
    detail: str


def _classification_stage(classification, dry_weight_kg) -> LotHistoryStage:
    split = quality_split(classification.g1_kg, classification.g2_kg, classification.discard_kg)
    return LotHistoryStage.at(
        "classification",
        classification.classified_at,
        recorded_at=classification.created_at,
        data=ClassificationData(
            classified_by=full_name(classification.classified_by),
            dry_weight_kg=dry_weight_kg,
            g1_kg=split["g1_kg"],
            g2_kg=split["g2_kg"],
            discard_kg=split["discard_kg"],
            g1_pct=split["g1_pct"],
            g2_pct=split["g2_pct"],
            discard_pct=split["discard_pct"],
            discard_reason=classification.discard_reason or None,
            discard_detail=classification.discard_detail,
        ),
    )


def _discard_stage(discard, dry_weight_kg) -> LotHistoryStage:
    return LotHistoryStage.at(
        "discard",
        discard.discarded_at,
        recorded_at=discard.created_at,
        data=DiscardData(
            discarded_by=full_name(discard.discarded_by),
            quantity_kg=dry_weight_kg,
            reason=discard.reason,
            detail=discard.detail,
        ),
    )


def quality_history(lot_id) -> list[LotHistoryStage]:
    # Sin evaluación no hay clasificación ni descarte: todo se trae desde ella, en una consulta.
    evaluation = (
        QualityEvaluation.objects.filter(lot_id=lot_id)
        .select_related(
            "evaluated_by",
            "lot__drying",
            "lot__classification__classified_by",
            "lot__discard__discarded_by",
        )
        .first()
    )
    if evaluation is None:
        return []
    lot = evaluation.lot
    stages = [
        LotHistoryStage.at(
            "evaluation",
            evaluation.evaluated_at,
            recorded_at=evaluation.created_at,
            data=EvaluationData(
                evaluated_by=full_name(evaluation.evaluated_by),
                well_fermented_pct=evaluation.well_fermented_pct,
                moldy_pct=evaluation.moldy_pct,
                other_defects_pct=evaluation.other_defects_pct,
                corrected_at=evaluation.corrected_at,
            ),
        )
    ]
    dry_weight_kg = lot.drying.dry_weight_kg
    classification = getattr(lot, "classification", None)
    if classification is not None:
        stages.append(_classification_stage(classification, dry_weight_kg))
    discard = getattr(lot, "discard", None)
    if discard is not None:
        stages.append(_discard_stage(discard, dry_weight_kg))
    return stages


def _percent(**kwargs):
    return serializers.DecimalField(max_digits=4, decimal_places=ONE_DECIMAL, **kwargs)


def _kilograms():
    return serializers.DecimalField(max_digits=7, decimal_places=ONE_DECIMAL)


class EvaluationStageSerializer(serializers.Serializer):
    evaluated_by = serializers.CharField()
    well_fermented_pct = _percent()
    moldy_pct = _percent()
    other_defects_pct = _percent()
    corrected_at = serializers.DateTimeField(allow_null=True)


class ClassificationStageSerializer(serializers.Serializer):
    classified_by = serializers.CharField()
    dry_weight_kg = _kilograms()
    g1_kg = _kilograms()
    g2_kg = _kilograms()
    discard_kg = _kilograms()
    g1_pct = _percent(allow_null=True)
    g2_pct = _percent(allow_null=True)
    discard_pct = _percent(allow_null=True)
    discard_reason = serializers.ChoiceField(choices=DiscardReason.choices, allow_null=True)
    discard_detail = serializers.CharField(allow_blank=True)


class DiscardStageSerializer(serializers.Serializer):
    discarded_by = serializers.CharField()
    quantity_kg = _kilograms()
    reason = serializers.ChoiceField(choices=DiscardReason.choices)
    detail = serializers.CharField(allow_blank=True)
