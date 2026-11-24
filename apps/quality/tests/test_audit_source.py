"""La calidad en la bitácora: los porcentajes, los calibres y el motivo del descarte."""

import pytest

from apps.common.contracts.audit_log import audit_source
from apps.lots.tests.factories import LotFactory
from apps.quality.services.audit import record_quality_event

pytestmark = pytest.mark.django_db


def test_a_classification_shows_its_kilograms_and_the_reason_by_its_label():
    lot = LotFactory()
    event = record_quality_event(
        lot=lot,
        actor=None,
        action="classified",
        before={},
        after={"g1_kg": "32.5", "discard_kg": "4.5", "discard_reason": "mold"},
        version=1,
    )

    [entry] = audit_source("quality").describe([event.pk])

    assert (entry.record_label, entry.action_label) == (lot.code, "Lote clasificado")
    changes = {change.field: change for change in entry.changes}
    assert (changes["g1_kg"].label, changes["g1_kg"].kind) == ("G1 (kg)", "number")
    assert changes["discard_reason"].after == "Moho"


def test_a_whole_discard_shows_its_reason():
    lot = LotFactory()
    event = record_quality_event(
        lot=lot,
        actor=None,
        action="discarded",
        before={},
        after={"reason": "contamination", "detail": "Humo"},
        version=1,
    )

    changes = {c.field: c for c in audit_source("quality").describe([event.pk])[0].changes}

    assert changes["reason"].label == "Motivo del descarte"
    assert changes["reason"].after == "Contaminación (humo, olores, químicos)"
