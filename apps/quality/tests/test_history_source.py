from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.common.contracts.lot_history import lot_history_source, stage_serializers
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.quality.history import ClassificationData, DiscardData, EvaluationData
from apps.quality.tests.factories import (
    LotClassificationFactory,
    LotDiscardFactory,
    QualityEvaluationFactory,
)
from apps.quality.tests.helpers import dried_lot

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")
EVALUATED = datetime(2026, 3, 30, 9, 15, tzinfo=BOGOTA)


def _history(lot):
    return lot_history_source("quality_history")(lot.pk)


def _evaluated(status, dry_weight="45.0"):
    lot = dried_lot(characterized_plot(), status=status, dry_weight=Decimal(dry_weight))
    evaluation = QualityEvaluationFactory(
        lot=lot,
        evaluated_at=EVALUATED,
        evaluated_by__first_name="Ana",
        evaluated_by__last_name="Ruiz",
    )
    return lot, evaluation


def test_a_lot_without_evaluation_has_no_quality_stages():
    assert _history(LotFactory()) == []


def test_an_evaluated_lot_has_only_its_evaluation():
    lot, evaluation = _evaluated(LotStatus.EVALUATED)

    [stage] = _history(lot)

    assert (stage.kind, stage.occurred_at, stage.recorded_at) == (
        "evaluation",
        EVALUATED,
        evaluation.created_at,
    )
    assert stage.data == EvaluationData(
        evaluated_by="Ana Ruiz",
        well_fermented_pct=Decimal("78.5"),
        moldy_pct=Decimal("2.0"),
        other_defects_pct=Decimal("4.5"),
        corrected_at=None,
    )


def test_a_corrected_evaluation_says_when_it_was_corrected():
    lot, evaluation = _evaluated(LotStatus.EVALUATED)
    evaluation.corrected_by = evaluation.evaluated_by
    evaluation.corrected_at = EVALUATED + timedelta(days=1)
    evaluation.save()

    [stage] = _history(lot)

    assert stage.data.corrected_at == EVALUATED + timedelta(days=1)


def test_a_classification_without_discard_has_no_reason():
    lot, _ = _evaluated(LotStatus.CLASSIFIED, dry_weight="40.5")
    classification = LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal("32.5"),
        g2_kg=Decimal("8.0"),
        classified_at=EVALUATED + timedelta(hours=2),
    )

    _, stage = _history(lot)

    assert (stage.kind, stage.occurred_at, stage.recorded_at) == (
        "classification",
        classification.classified_at,
        classification.created_at,
    )
    assert stage.data.discard_kg == Decimal("0.0")
    assert stage.data.discard_pct == Decimal("0.0")
    assert (stage.data.discard_reason, stage.data.discard_detail) == (None, "")


def test_a_partial_discard_brings_its_quantity_and_reason():
    lot, _ = _evaluated(LotStatus.CLASSIFIED)
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal("32.5"),
        g2_kg=Decimal("8.0"),
        discard_kg=Decimal("4.5"),
        discard_reason="other",
        discard_detail="Granos partidos",
        classified_by__first_name="Ana",
        classified_by__last_name="Ruiz",
    )

    _, stage = _history(lot)

    assert stage.data == ClassificationData(
        classified_by="Ana Ruiz",
        dry_weight_kg=Decimal("45.0"),
        g1_kg=Decimal("32.5"),
        g2_kg=Decimal("8.0"),
        discard_kg=Decimal("4.5"),
        g1_pct=Decimal("72.2"),
        g2_pct=Decimal("17.8"),
        discard_pct=Decimal("10.0"),
        discard_reason="other",
        discard_detail="Granos partidos",
    )


def test_a_whole_discard_is_the_dry_weight_of_the_lot():
    lot, _ = _evaluated(LotStatus.DISCARDED, dry_weight="38.5")
    discard = LotDiscardFactory(
        lot=lot,
        discarded_at=EVALUATED + timedelta(days=1),
        discarded_by__first_name="Ana",
        discarded_by__last_name="Ruiz",
    )

    kinds = [stage.kind for stage in _history(lot)]
    stage = _history(lot)[-1]

    assert kinds == ["evaluation", "discard"]
    assert (stage.occurred_at, stage.recorded_at) == (discard.discarded_at, discard.created_at)
    assert stage.data == DiscardData(
        discarded_by="Ana Ruiz", quantity_kg=Decimal("38.5"), reason="mold", detail=""
    )


def test_the_quality_stages_take_one_query(django_assert_num_queries):
    lot, _ = _evaluated(LotStatus.CLASSIFIED)
    LotClassificationFactory(lot=lot, g1_kg=Decimal("40.0"), g2_kg=Decimal("5.0"))

    with django_assert_num_queries(1):
        stages = _history(lot)

    assert len(stages) == 2


def test_the_quality_stages_are_serialized_with_their_reason_codes():
    lot, _ = _evaluated(LotStatus.CLASSIFIED)
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal("32.5"),
        g2_kg=Decimal("8"),
        discard_kg=Decimal("4.5"),
        discard_reason="mold",
    )
    evaluation, classification = _history(lot)
    serializers = stage_serializers()

    assert serializers["evaluation"].to_representation(evaluation.data)["moldy_pct"] == "2.0"
    data = serializers["classification"].to_representation(classification.data)
    assert (data["g2_kg"], data["discard_pct"], data["discard_reason"]) == ("8.0", "10.0", "mold")
