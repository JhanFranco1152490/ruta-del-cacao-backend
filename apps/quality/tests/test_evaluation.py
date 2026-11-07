"""Registrar y corregir la evaluación física de un lote."""

from decimal import Decimal

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role
from apps.lots.choices import LotStatus
from apps.quality.models import QualityAuditEvent, QualityEvaluation

from .helpers import QualityEstate, classified, discarded, dried_lot

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return QualityEstate()


def url(lot):
    return f"/api/quality/{lot.pk}/evaluation"


def body(lot, **overrides):
    return {
        "expected_lot_version": lot.version,
        "well_fermented_pct": "78.5",
        "moldy_pct": "2.0",
        "other_defects_pct": "4.5",
        **overrides,
    }


def evaluate(client, lot, **overrides):
    return client.post(url(lot), body(lot, **overrides), format="json")


# --- Registrar (HU-34) ---


def test_evaluating_a_dried_lot_leaves_it_evaluated(auth_client, estate):
    lot = estate.dried_old

    response = evaluate(auth_client(estate.inspector), lot, notes="Corte de 300 granos")

    assert response.status_code == 201, response.data
    assert response.data["lot"]["status"] == "evaluated"
    evaluation = response.data["evaluation"]
    assert (evaluation["well_fermented_pct"], evaluation["moldy_pct"]) == ("78.5", "2.0")
    assert (evaluation["other_defects_pct"], evaluation["notes"]) == ("4.5", "Corte de 300 granos")
    assert evaluation["evaluated_by"]["id"] == str(estate.inspector.pk)
    assert evaluation["evaluated_at"] is not None
    assert evaluation["version"] == 1
    lot.refresh_from_db()
    assert (lot.status, lot.version) == ("evaluated", 2)


def test_evaluating_leaves_the_history_of_the_lot_and_of_its_quality(auth_client, estate):
    lot = estate.dried_old

    evaluate(auth_client(estate.inspector), lot)

    event = QualityAuditEvent.objects.get(lot=lot)
    assert (event.action, event.actor, event.version) == ("evaluated", estate.inspector, 1)
    assert event.changes["moldy_pct"] == {"before": None, "after": "2.0"}
    status = lot.audit_events.get(action="status_changed")
    assert status.changes == {"status": {"before": "dried", "after": "evaluated"}}


@pytest.mark.parametrize("field", ["well_fermented_pct", "moldy_pct", "other_defects_pct"])
def test_every_percentage_is_required(auth_client, estate, field):
    payload = body(estate.dried_old)
    del payload[field]

    response = auth_client(estate.owner).post(url(estate.dried_old), payload, format="json")

    assert response.status_code == 400
    assert field in response.data["fields"]


@pytest.mark.parametrize("value", ["-0.1", "100.1", "120"])
def test_a_percentage_out_of_range_is_refused(auth_client, estate, value):
    response = evaluate(auth_client(estate.owner), estate.dried_old, moldy_pct=value)

    assert response.status_code == 400
    assert response.data["fields"]["moldy_pct"] == ["El valor debe estar entre 0 y 100"]
    assert not QualityEvaluation.objects.filter(lot=estate.dried_old).exists()


def test_a_percentage_with_two_decimals_is_refused(auth_client, estate):
    response = evaluate(auth_client(estate.owner), estate.dried_old, moldy_pct="2.05")

    assert response.status_code == 400
    assert "moldy_pct" in response.data["fields"]


def test_notes_longer_than_500_are_refused(auth_client, estate):
    response = evaluate(auth_client(estate.owner), estate.dried_old, notes="x" * 501)

    assert response.status_code == 400
    assert "notes" in response.data["fields"]


def test_an_unknown_field_is_refused(auth_client, estate):
    response = evaluate(auth_client(estate.owner), estate.dried_old, grade="G1")

    assert response.status_code == 400


def test_the_three_percentages_can_add_up_to_exactly_100(auth_client, estate):
    response = evaluate(
        auth_client(estate.owner),
        estate.dried_old,
        well_fermented_pct="80.0",
        moldy_pct="15.0",
        other_defects_pct="5.0",
    )

    assert response.status_code == 201


def test_three_percentages_above_100_are_refused_with_their_total(auth_client, estate):
    response = evaluate(
        auth_client(estate.owner),
        estate.dried_old,
        well_fermented_pct="80.0",
        moldy_pct="15.0",
        other_defects_pct="10.0",
    )

    assert response.status_code == 400
    assert response.data["code"] == "quality_sum_exceeds_100"
    assert response.data["total_pct"] == "105.0"
    assert response.data["fields"]["non_field_errors"] == ["La suma no puede pasar de 100 %"]
    estate.dried_old.refresh_from_db()
    assert estate.dried_old.status == "dried"


@pytest.mark.parametrize("lot_name", ["drying", "evaluated", "classified", "discarded"])
def test_only_a_dried_lot_is_evaluated(auth_client, estate, lot_name):
    lot = getattr(estate, lot_name)

    response = evaluate(auth_client(estate.owner), lot)

    assert response.status_code == 409
    assert response.data["code"] == "lot_invalid_status"
    assert response.data["current_status"] == lot.status


def test_evaluating_twice_the_same_lot_refuses_the_second(auth_client, estate):
    client = auth_client(estate.owner)
    lot = estate.dried_old
    first = body(lot)

    assert client.post(url(lot), first, format="json").status_code == 201
    second = client.post(url(lot), first, format="json")

    assert second.status_code == 409
    assert second.data["code"] == "lot_invalid_status"
    assert QualityEvaluation.objects.filter(lot=lot).count() == 1


def test_a_stale_lot_version_is_refused_with_the_current_one(auth_client, estate):
    response = evaluate(auth_client(estate.owner), estate.dried_old, expected_lot_version=7)

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["lot"]["version"] == 1


def test_a_failure_while_advancing_the_lot_leaves_nothing(auth_client, estate, monkeypatch):
    lot_model = type(estate.dried_old)

    def broken(self, *args, **kwargs):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(lot_model, "advance_status", broken)
    client = auth_client(estate.owner)
    client.raise_request_exception = False

    response = evaluate(client, estate.dried_old)

    assert response.status_code == 500
    assert not QualityEvaluation.objects.filter(lot=estate.dried_old).exists()
    assert not QualityAuditEvent.objects.filter(lot=estate.dried_old).exists()


def test_a_lot_outside_the_reach_is_404(auth_client, estate):
    response = evaluate(auth_client(estate.inspector), estate.dried_b)

    assert response.status_code == 404


def test_another_producer_cannot_evaluate(auth_client, estate):
    other = QualityEstate()

    assert evaluate(auth_client(other.owner), estate.dried_old).status_code == 404


def test_without_the_permission_it_is_403(auth_client, estate):
    foreman = grant_role(
        UserFactory(producer=estate.producer, farm=estate.farm_a), get_system_role(FOREMAN)
    )

    assert evaluate(auth_client(foreman), estate.dried_old).status_code == 403


# --- Corregir (HU-35) ---


def correct(client, lot, **changes):
    payload = {"expected_version": lot.quality_evaluation.version, **changes}
    return client.patch(url(lot), payload, format="json")


def test_correcting_updates_the_evaluation_and_who_corrected(auth_client, estate):
    lot = estate.evaluated

    response = correct(auth_client(estate.owner), lot, moldy_pct="3.0")

    assert response.status_code == 200, response.data
    evaluation = response.data["evaluation"]
    assert evaluation["moldy_pct"] == "3.0"
    assert evaluation["corrected_by"]["id"] == str(estate.owner.pk)
    assert evaluation["corrected_at"] is not None
    assert evaluation["version"] == 2
    # Quien evaluó sigue siendo el mismo.
    assert evaluation["evaluated_by"]["id"] == str(estate.inspector.pk)
    assert response.data["lot"]["status"] == "evaluated"


def test_correcting_leaves_only_what_changed_in_the_history(auth_client, estate):
    lot = estate.evaluated

    correct(auth_client(estate.owner), lot, moldy_pct="3.0", notes="Recontado")

    event = QualityAuditEvent.objects.get(lot=lot, action="evaluation_corrected")
    assert (event.actor, event.version) == (estate.owner, 2)
    assert event.changes == {
        "moldy_pct": {"before": "2.0", "after": "3.0"},
        "notes": {"before": "", "after": "Recontado"},
    }


def test_correcting_without_real_changes_writes_nothing(auth_client, estate):
    lot = estate.evaluated

    response = correct(auth_client(estate.owner), lot, moldy_pct="2.0")

    assert response.status_code == 200
    assert response.data["evaluation"]["version"] == 1
    assert response.data["evaluation"]["corrected_by"] is None
    assert not QualityAuditEvent.objects.filter(lot=lot).exists()


def test_a_correction_cannot_take_the_total_above_100(auth_client, estate):
    response = correct(auth_client(estate.owner), estate.evaluated, well_fermented_pct="95.0")

    assert response.status_code == 400
    assert response.data["code"] == "quality_sum_exceeds_100"


@pytest.mark.parametrize("closing", [classified, discarded])
def test_a_classified_or_discarded_lot_cannot_be_corrected(auth_client, estate, closing):
    status = LotStatus.CLASSIFIED if closing is classified else LotStatus.DISCARDED
    lot = dried_lot(estate.plot_a, status=status)
    closing(lot, estate.owner)

    response = correct(auth_client(estate.owner), lot, moldy_pct="3.0")

    assert response.status_code == 409
    assert response.data["code"] == "lot_invalid_status"
    assert response.data["current_status"] == status


def test_a_stale_correction_is_refused_with_the_current_evaluation(auth_client, estate):
    client = auth_client(estate.owner)
    lot = estate.evaluated
    assert correct(client, lot, moldy_pct="3.0").status_code == 200

    response = client.patch(url(lot), {"expected_version": 1, "moldy_pct": "4.0"}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["evaluation"]["moldy_pct"] == "3.0"


def test_a_correction_needs_the_version_and_some_change(auth_client, estate):
    client = auth_client(estate.owner)
    lot = estate.evaluated

    without_version = client.patch(url(lot), {"moldy_pct": "3.0"}, format="json")
    without_changes = client.patch(url(lot), {"expected_version": 1}, format="json")

    assert without_version.status_code == 400
    assert "expected_version" in without_version.data["fields"]
    assert without_changes.status_code == 400


def test_a_dried_lot_has_no_evaluation_to_correct(auth_client, estate):
    response = auth_client(estate.owner).patch(
        url(estate.dried_old), {"expected_version": 1, "moldy_pct": "3.0"}, format="json"
    )

    assert response.status_code == 409
    assert response.data["current_status"] == "dried"


def test_correcting_needs_the_permission(auth_client, estate):
    foreman = grant_role(
        UserFactory(producer=estate.producer, farm=estate.farm_a), get_system_role(FOREMAN)
    )

    assert correct(auth_client(foreman), estate.evaluated, moldy_pct="3.0").status_code == 403


def test_a_correction_with_a_wrong_percentage_keeps_the_evaluation(auth_client, estate):
    response = correct(auth_client(estate.owner), estate.evaluated, moldy_pct="100.1")

    assert response.status_code == 400
    assert estate.evaluated.quality_evaluation.moldy_pct == Decimal("2.0")
