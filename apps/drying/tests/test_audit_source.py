"""El secado en la bitácora: la marquesina por su nombre, el clima por su etiqueta y la bitácora
dentro de su lote."""

import pytest

from apps.common.contracts.audit_log import audit_source
from apps.drying.services.audit import record_process_event
from apps.drying.tests.factories import DryingProcessFactory

pytestmark = pytest.mark.django_db


def test_a_log_is_named_inside_its_lot_with_its_weather():
    process = DryingProcessFactory()
    event = record_process_event(
        process=process,
        actor=None,
        action="log_created",
        before={},
        after={"moisture_pct": "45.0", "weather": "sunny"},
        log_ref=process.lot_id,
    )

    [entry] = audit_source("drying").describe([event.pk])

    assert entry.record_label == f"Lote {process.lot.code} · bitácora"
    changes = {change.field: change for change in entry.changes}
    assert changes["weather"].after == "Soleado"
    assert (changes["moisture_pct"].label, changes["moisture_pct"].kind) == (
        "Humedad (%)",
        "number",
    )


def test_a_start_shows_the_dryer_by_name():
    process = DryingProcessFactory(facility__name="M-02")
    event = record_process_event(
        process=process,
        actor=None,
        action="started",
        before={},
        after={"facility_id": process.facility_id, "entry_moisture_pct": "55.0"},
    )

    [entry] = audit_source("drying").describe([event.pk])

    assert entry.record_label == f"Lote {process.lot.code}"
    changes = {change.field: change for change in entry.changes}
    assert changes["facility_id"].after == "M-02"
    assert changes["entry_moisture_pct"].label == "Humedad de entrada (%)"
