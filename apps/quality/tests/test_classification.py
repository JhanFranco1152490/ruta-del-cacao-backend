"""Clasificar un lote evaluado por calibre (HU-36)."""

import pytest

from apps.accounts.tests.role_helpers import make_delegate
from apps.lots.choices import LotStatus
from apps.quality.models import LotClassification, QualityAuditEvent

from .helpers import QualityEstate, classified, discarded, dried_lot

pytestmark = pytest.mark.django_db

# El lote evaluado de la finca pesa 313,2 kg secos.


@pytest.fixture
def estate():
    return QualityEstate()


def url(lot):
    return f"/api/quality/{lot.pk}/classification"


def body(lot, **overrides):
    return {
        "expected_lot_version": lot.version,
        "g1_kg": "250.0",
        "g2_kg": "55.2",
        "discard_kg": "8.0",
        "discard_reason": "mold",
        **overrides,
    }


def classify(client, lot, **overrides):
    return client.post(url(lot), body(lot, **overrides), format="json")


def test_classifying_an_evaluated_lot_leaves_it_classified(auth_client, estate):
    lot = estate.evaluated

    response = classify(auth_client(estate.inspector), lot)

    assert response.status_code == 201, response.data
    assert response.data["lot"]["status"] == "classified"
    classification = response.data["classification"]
    assert (classification["g1_kg"], classification["g2_kg"]) == ("250.0", "55.2")
    assert (classification["discard_kg"], classification["discard_reason"]) == ("8.0", "mold")
    assert classification["classified_by"]["id"] == str(estate.inspector.pk)
    lot.refresh_from_db()
    assert lot.status == "classified"


def test_classifying_leaves_the_history(auth_client, estate):
    lot = estate.evaluated

    classify(auth_client(estate.inspector), lot)

    event = QualityAuditEvent.objects.get(lot=lot, action="classified")
    assert event.actor == estate.inspector
    assert event.changes["g1_kg"] == {"before": None, "after": "250.0"}
    assert event.changes["discard_reason"] == {"before": None, "after": "mold"}
    status = lot.audit_events.get(action="status_changed")
    assert status.changes == {"status": {"before": "evaluated", "after": "classified"}}


def test_the_lot_shows_its_grades_for_storage(auth_client, estate):
    client = auth_client(estate.owner)

    classify(client, estate.evaluated)

    quality = client.get(f"/api/lots/{estate.evaluated.pk}").data["quality"]
    assert (quality["g1_kg"], quality["g2_kg"], quality["discard_kg"]) == (
        "250.0",
        "55.2",
        "8.0",
    )


def test_without_discard_no_reason_is_asked(auth_client, estate):
    response = classify(
        auth_client(estate.owner),
        estate.evaluated,
        g2_kg="63.2",
        discard_kg="0.0",
        discard_reason="",
    )

    assert response.status_code == 201, response.data
    assert response.data["classification"]["discard_reason"] == ""


def test_the_kilos_must_add_up_to_the_dry_weight_with_its_decimals(auth_client, estate):
    response = classify(
        auth_client(estate.owner),
        estate.evaluated,
        g1_kg="200.1",
        g2_kg="100.0",
        discard_kg="13.1",
    )

    assert response.status_code == 201, response.data


def test_missing_kilos_are_refused_with_the_difference(auth_client, estate):
    response = classify(
        auth_client(estate.owner),
        estate.evaluated,
        g2_kg="50.0",
        discard_kg="0.0",
        discard_reason="",
    )

    assert response.status_code == 400
    assert response.data["code"] == "classification_sum_mismatch"
    assert response.data["fields"]["non_field_errors"] == ["Faltan 13,2 kg por distribuir"]
    assert (response.data["expected_kg"], response.data["received_kg"]) == ("313.2", "300.0")
    assert response.data["difference_kg"] == "13.2"
    assert not LotClassification.objects.filter(lot=estate.evaluated).exists()


def test_extra_kilos_are_refused_with_the_difference(auth_client, estate):
    response = classify(auth_client(estate.owner), estate.evaluated, g2_kg="60.0")

    assert response.status_code == 400
    assert response.data["fields"]["non_field_errors"] == ["Sobran 4,8 kg"]
    assert response.data["difference_kg"] == "-4.8"


@pytest.mark.parametrize("field", ["g1_kg", "g2_kg", "discard_kg"])
def test_negative_kilos_are_refused(auth_client, estate, field):
    response = classify(auth_client(estate.owner), estate.evaluated, **{field: "-0.1"})

    assert response.status_code == 400
    assert field in response.data["fields"]


def test_kilos_with_two_decimals_are_refused(auth_client, estate):
    response = classify(auth_client(estate.owner), estate.evaluated, g1_kg="250.05")

    assert response.status_code == 400
    assert "g1_kg" in response.data["fields"]


@pytest.mark.parametrize("field", ["g1_kg", "g2_kg", "discard_kg"])
def test_every_weight_is_required(auth_client, estate, field):
    payload = body(estate.evaluated)
    del payload[field]

    response = auth_client(estate.owner).post(url(estate.evaluated), payload, format="json")

    assert response.status_code == 400
    assert field in response.data["fields"]


def test_a_partial_discard_without_reason_is_refused(auth_client, estate):
    response = classify(auth_client(estate.owner), estate.evaluated, discard_reason="")

    assert response.status_code == 400
    assert response.data["fields"]["discard_reason"] == ["Indique el motivo del descarte"]


def test_a_reason_without_discard_is_refused(auth_client, estate):
    response = classify(auth_client(estate.owner), estate.evaluated, g2_kg="63.2", discard_kg="0")

    assert response.status_code == 400
    assert "discard_reason" in response.data["fields"]


def test_other_as_reason_needs_its_detail(auth_client, estate):
    client = auth_client(estate.owner)

    without = classify(client, estate.evaluated, discard_reason="other")
    with_detail = classify(
        client, estate.evaluated, discard_reason="other", discard_detail="Granos partidos"
    )

    assert without.status_code == 400
    assert without.data["fields"]["discard_detail"] == ["Describa el motivo del descarte"]
    assert with_detail.status_code == 201
    assert with_detail.data["classification"]["discard_detail"] == "Granos partidos"


def test_a_reason_outside_the_list_is_refused(auth_client, estate):
    response = classify(auth_client(estate.owner), estate.evaluated, discard_reason="bad_luck")

    assert response.status_code == 400
    assert "discard_reason" in response.data["fields"]


@pytest.mark.parametrize("status", [LotStatus.DRIED, LotStatus.CLASSIFIED, LotStatus.DISCARDED])
def test_only_an_evaluated_lot_is_classified(auth_client, estate, status):
    lot = dried_lot(estate.plot_a, status=status)
    if status == LotStatus.CLASSIFIED:
        classified(lot, estate.owner)
    if status == LotStatus.DISCARDED:
        discarded(lot, estate.owner)

    response = classify(auth_client(estate.owner), lot)

    assert response.status_code == 409
    assert response.data["code"] == "lot_invalid_status"
    assert response.data["current_status"] == status


def test_classifying_twice_refuses_the_second(auth_client, estate):
    client = auth_client(estate.owner)
    payload = body(estate.evaluated)

    assert client.post(url(estate.evaluated), payload, format="json").status_code == 201
    second = client.post(url(estate.evaluated), payload, format="json")

    assert second.status_code == 409
    assert second.data["code"] == "lot_invalid_status"
    assert LotClassification.objects.filter(lot=estate.evaluated).count() == 1


def test_a_stale_lot_version_is_refused_with_the_current_one(auth_client, estate):
    response = classify(auth_client(estate.owner), estate.evaluated, expected_lot_version=7)

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["lot"]["status"] == "evaluated"


def test_a_failure_while_advancing_the_lot_leaves_nothing(auth_client, estate, monkeypatch):
    def broken(self, *args, **kwargs):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(type(estate.evaluated), "advance_status", broken)
    client = auth_client(estate.owner)
    client.raise_request_exception = False

    response = classify(client, estate.evaluated)

    assert response.status_code == 500
    assert not LotClassification.objects.filter(lot=estate.evaluated).exists()
    assert not QualityAuditEvent.objects.filter(lot=estate.evaluated).exists()


def test_evaluating_is_not_enough_to_classify(auth_client, estate):
    evaluator = make_delegate(estate.producer, ["quality.evaluate_lot"], farm=estate.farm_a)

    assert classify(auth_client(evaluator), estate.evaluated).status_code == 403


def test_a_lot_outside_the_reach_is_404(auth_client, estate):
    lot = dried_lot(estate.plot_b, status=LotStatus.EVALUATED)

    assert classify(auth_client(estate.inspector), lot).status_code == 404
