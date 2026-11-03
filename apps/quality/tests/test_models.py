from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.quality.choices import DiscardReason
from apps.quality.models import QualityAuditEvent

from .factories import LotClassificationFactory, LotDiscardFactory, QualityEvaluationFactory

pytestmark = pytest.mark.django_db

PERCENTAGES = ("well_fermented_pct", "moldy_pct", "other_defects_pct")


def refused(build):
    """Que la base rechace lo que crea `build`, sin romper la transacción de la prueba."""
    with pytest.raises(IntegrityError), transaction.atomic():
        build()


# --- La evaluación ---


def test_a_new_evaluation_has_not_been_corrected():
    evaluation = QualityEvaluationFactory()

    assert (evaluation.corrected_by, evaluation.corrected_at, evaluation.version) == (
        None,
        None,
        1,
    )
    assert evaluation.notes == ""


@pytest.mark.parametrize("field", PERCENTAGES)
@pytest.mark.parametrize("value", ["0.0", "100.0"])
def test_each_percentage_goes_from_0_to_100(field, value):
    others = {name: Decimal("0.0") for name in PERCENTAGES if name != field}

    assert QualityEvaluationFactory(**others, **{field: Decimal(value)}).pk


@pytest.mark.parametrize("field", PERCENTAGES)
@pytest.mark.parametrize("value", ["-0.1", "100.1"])
def test_a_percentage_out_of_range_is_refused(field, value):
    others = {name: Decimal("0.0") for name in PERCENTAGES if name != field}

    refused(lambda: QualityEvaluationFactory(**others, **{field: Decimal(value)}))


def test_the_three_percentages_can_add_up_to_100():
    evaluation = QualityEvaluationFactory(
        well_fermented_pct=Decimal("80.0"),
        moldy_pct=Decimal("15.0"),
        other_defects_pct=Decimal("5.0"),
    )

    assert evaluation.pk


def test_the_three_percentages_cannot_add_up_to_more_than_100():
    refused(
        lambda: QualityEvaluationFactory(
            well_fermented_pct=Decimal("80.0"),
            moldy_pct=Decimal("15.0"),
            other_defects_pct=Decimal("5.1"),
        )
    )


def test_a_correction_keeps_who_corrected_and_when_together():
    evaluation = QualityEvaluationFactory()

    refused(
        lambda: QualityEvaluationFactory(corrected_by=evaluation.evaluated_by, corrected_at=None)
    )
    refused(lambda: QualityEvaluationFactory(corrected_by=None, corrected_at=timezone.now()))


def test_the_lot_and_the_evaluator_are_protected():
    evaluation = QualityEvaluationFactory()

    with pytest.raises(ProtectedError):
        evaluation.lot.delete()
    with pytest.raises(ProtectedError):
        evaluation.evaluated_by.delete()


def test_the_lot_reaches_its_evaluation():
    evaluation = QualityEvaluationFactory()

    assert evaluation.lot.quality_evaluation == evaluation


# --- La clasificación ---


def test_a_classification_without_discard_has_no_reason():
    classification = LotClassificationFactory()

    assert (classification.discard_reason, classification.discard_detail) == ("", "")
    assert classification.lot.classification == classification


@pytest.mark.parametrize("field", ["g1_kg", "g2_kg", "discard_kg"])
def test_no_weight_can_be_negative(field):
    refused(lambda: LotClassificationFactory(**{field: Decimal("-0.1")}))


def test_a_partial_discard_carries_its_reason():
    classification = LotClassificationFactory(
        g2_kg=Decimal("55.2"), discard_kg=Decimal("8.0"), discard_reason=DiscardReason.MOLD
    )

    assert classification.discard_reason == "mold"


def test_a_partial_discard_without_reason_is_refused():
    refused(lambda: LotClassificationFactory(g2_kg=Decimal("55.2"), discard_kg=Decimal("8.0")))


def test_a_reason_without_discard_is_refused():
    refused(lambda: LotClassificationFactory(discard_reason=DiscardReason.MOLD))


def test_a_reason_outside_the_list_is_refused():
    refused(
        lambda: LotClassificationFactory(
            g2_kg=Decimal("55.2"), discard_kg=Decimal("8.0"), discard_reason="bad_luck"
        )
    )


def test_other_as_partial_reason_needs_its_detail():
    refused(
        lambda: LotClassificationFactory(
            g2_kg=Decimal("55.2"), discard_kg=Decimal("8.0"), discard_reason=DiscardReason.OTHER
        )
    )
    assert LotClassificationFactory(
        g2_kg=Decimal("55.2"),
        discard_kg=Decimal("8.0"),
        discard_reason=DiscardReason.OTHER,
        discard_detail="Granos partidos",
    ).pk


def test_the_lot_and_the_classifier_are_protected():
    classification = LotClassificationFactory()

    with pytest.raises(ProtectedError):
        classification.lot.delete()
    with pytest.raises(ProtectedError):
        classification.classified_by.delete()


# --- El descarte completo ---


def test_a_discard_carries_its_reason():
    discard = LotDiscardFactory()

    assert (discard.reason, discard.detail) == ("mold", "")
    assert discard.lot.discard == discard


def test_a_discard_without_reason_or_outside_the_list_is_refused():
    refused(lambda: LotDiscardFactory(reason=""))
    refused(lambda: LotDiscardFactory(reason="bad_luck"))


def test_other_as_discard_reason_needs_its_detail():
    refused(lambda: LotDiscardFactory(reason=DiscardReason.OTHER))
    assert LotDiscardFactory(reason=DiscardReason.OTHER, detail="Agua de lluvia").pk


def test_the_lot_and_who_discarded_are_protected():
    discard = LotDiscardFactory()

    with pytest.raises(ProtectedError):
        discard.lot.delete()
    with pytest.raises(ProtectedError):
        discard.discarded_by.delete()


# --- El historial ---


def test_the_history_keeps_the_lot_and_the_change():
    evaluation = QualityEvaluationFactory()

    event = QualityAuditEvent.record(
        lot=evaluation.lot,
        actor=evaluation.evaluated_by,
        action=QualityAuditEvent.Action.EVALUATED,
        version=1,
        changes={"moldy_pct": {"before": None, "after": "2.0"}},
    )

    assert evaluation.lot.quality_audit_events.get() == event
    with pytest.raises(ProtectedError):
        evaluation.lot.delete()


def test_the_history_only_takes_its_own_actions():
    evaluation = QualityEvaluationFactory()

    with pytest.raises(ValueError):
        QualityAuditEvent.record(
            lot=evaluation.lot, actor=None, action="sold", version=1, changes={}
        )


def test_the_history_survives_the_account_that_acted():
    evaluation = QualityEvaluationFactory()
    actor = UserFactory(producer=evaluation.lot.harvest.plot.farm.producer)
    event = QualityAuditEvent.record(
        lot=evaluation.lot, actor=actor, action=QualityAuditEvent.Action.EVALUATED, version=1
    )

    actor.delete()

    event.refresh_from_db()
    assert event.actor is None
