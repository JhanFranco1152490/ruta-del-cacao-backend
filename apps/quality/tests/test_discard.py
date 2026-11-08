"""Descartar un lote completo (HU-37) y avisar a quienes trabajan la calidad en su finca."""

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate
from apps.lots.choices import LotStatus
from apps.notifications.models import Notification
from apps.quality.models import LotDiscard, QualityAuditEvent

from .helpers import QualityEstate, classified, dried_lot

pytestmark = pytest.mark.django_db

EVALUATE = "quality.evaluate_lot"


@pytest.fixture
def estate():
    return QualityEstate()


def url(lot, action="discard"):
    return f"/api/quality/{lot.pk}/{action}"


def body(lot, **overrides):
    return {"expected_lot_version": lot.version, "reason": "mold", **overrides}


def discard(client, lot, **overrides):
    return client.post(url(lot), body(lot, **overrides), format="json")


def test_discarding_an_evaluated_lot_leaves_it_discarded(auth_client, estate):
    lot = estate.evaluated

    response = discard(auth_client(estate.inspector), lot, detail="Moho en el 30 % del corte")

    assert response.status_code == 201, response.data
    assert response.data["lot"]["status"] == "discarded"
    assert response.data["discard"]["reason"] == "mold"
    assert response.data["discard"]["detail"] == "Moho en el 30 % del corte"
    assert response.data["discard"]["discarded_by"]["id"] == str(estate.inspector.pk)
    assert response.data["classification"] is None
    lot.refresh_from_db()
    assert lot.status == "discarded"


def test_discarding_leaves_the_history(auth_client, estate):
    lot = estate.evaluated

    discard(auth_client(estate.inspector), lot)

    event = QualityAuditEvent.objects.get(lot=lot, action="discarded")
    assert event.actor == estate.inspector
    assert event.changes["reason"] == {"before": None, "after": "mold"}
    status = lot.audit_events.get(action="status_changed")
    assert status.changes == {"status": {"before": "evaluated", "after": "discarded"}}


def test_the_reason_is_required(auth_client, estate):
    payload = body(estate.evaluated)
    del payload["reason"]

    response = auth_client(estate.owner).post(url(estate.evaluated), payload, format="json")

    assert response.status_code == 400
    assert response.data["fields"]["reason"] == ["Indique el motivo del descarte"]
    assert not LotDiscard.objects.filter(lot=estate.evaluated).exists()


def test_an_empty_reason_is_refused_with_the_same_message(auth_client, estate):
    response = discard(auth_client(estate.owner), estate.evaluated, reason="")

    assert response.status_code == 400
    assert response.data["fields"]["reason"] == ["Indique el motivo del descarte"]


def test_other_as_reason_needs_its_detail(auth_client, estate):
    client = auth_client(estate.owner)

    without = discard(client, estate.evaluated, reason="other")
    with_detail = discard(client, estate.evaluated, reason="other", detail="Agua de lluvia")

    assert without.status_code == 400
    assert without.data["fields"]["detail"] == ["Describa el motivo del descarte"]
    assert with_detail.status_code == 201


def test_a_reason_outside_the_list_or_a_long_detail_is_refused(auth_client, estate):
    client = auth_client(estate.owner)

    assert discard(client, estate.evaluated, reason="bad_luck").status_code == 400
    assert discard(client, estate.evaluated, detail="x" * 301).status_code == 400


@pytest.mark.parametrize("lot_name", ["dried_old", "classified", "discarded"])
def test_only_an_evaluated_lot_is_discarded(auth_client, estate, lot_name):
    lot = getattr(estate, lot_name)

    response = discard(auth_client(estate.owner), lot)

    assert response.status_code == 409
    assert response.data["code"] == "lot_invalid_status"
    assert response.data["current_status"] == lot.status


def test_a_discarded_lot_cannot_be_classified(auth_client, estate):
    client = auth_client(estate.owner)
    lot = estate.evaluated
    assert discard(client, lot).status_code == 201
    lot.refresh_from_db()

    response = client.post(
        url(lot, "classification"),
        {"expected_lot_version": lot.version, "g1_kg": "313.2", "g2_kg": "0", "discard_kg": "0"},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["current_status"] == "discarded"


def test_a_classified_lot_cannot_be_discarded(auth_client, estate):
    lot = dried_lot(estate.plot_a, status=LotStatus.CLASSIFIED)
    classified(lot, estate.owner)

    response = discard(auth_client(estate.owner), lot)

    assert response.status_code == 409
    assert response.data["current_status"] == "classified"


def test_a_stale_lot_version_is_refused_with_the_current_one(auth_client, estate):
    response = discard(auth_client(estate.owner), estate.evaluated, expected_lot_version=7)

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["lot"]["status"] == "evaluated"


def test_classifying_is_not_enough_to_discard(auth_client, estate):
    classifier = make_delegate(
        estate.producer, [EVALUATE, "quality.classify_lot"], farm=estate.farm_a
    )

    assert discard(auth_client(classifier), estate.evaluated).status_code == 403


def test_a_lot_outside_the_reach_is_404(auth_client, estate):
    lot = dried_lot(estate.plot_b, status=LotStatus.EVALUATED)

    assert discard(auth_client(estate.inspector), lot).status_code == 404


# --- El aviso ---


def notified(lot):
    return set(
        Notification.objects.filter(lot=lot, kind="lot_discarded").values_list(
            "recipient_id", flat=True
        )
    )


def test_the_quality_team_of_the_farm_is_notified(
    auth_client, estate, django_capture_on_commit_callbacks
):
    custom = make_delegate(estate.producer, [EVALUATE], farm=estate.farm_a)
    all_farms = make_delegate(estate.producer, [EVALUATE], all_farms=True)
    other_farm = make_delegate(estate.producer, [EVALUATE], farm=estate.farm_b)
    without_permission = grant_role(
        UserFactory(producer=estate.producer, farm=estate.farm_a), get_system_role(FOREMAN)
    )
    inactive = make_delegate(estate.producer, [EVALUATE], farm=estate.farm_a)
    inactive.is_active = False
    inactive.save()

    with django_capture_on_commit_callbacks(execute=True):
        response = discard(auth_client(estate.inspector), estate.evaluated)

    assert response.status_code == 201
    recipients = notified(estate.evaluated)
    assert recipients == {estate.owner.pk, custom.pk, all_farms.pk}
    assert not recipients & {
        estate.inspector.pk,
        other_farm.pk,
        without_permission.pk,
        inactive.pk,
    }


def test_whoever_discards_is_not_notified(auth_client, estate, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        discard(auth_client(estate.owner), estate.evaluated)

    assert notified(estate.evaluated) == {estate.inspector.pk}


def test_the_notice_names_the_lot_and_groups_by_its_quality(
    auth_client, estate, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        discard(auth_client(estate.inspector), estate.evaluated)

    notice = Notification.objects.get(recipient=estate.owner, kind="lot_discarded")
    assert notice.condition_key == f"{estate.evaluated.pk}:discarded"
    assert notice.thread_key == f"lot:{estate.evaluated.pk}:quality"
    assert notice.severity == "normal"


def test_the_owner_sees_the_notice_in_the_inbox(
    auth_client, estate, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        discard(auth_client(estate.inspector), estate.evaluated)

    response = auth_client(estate.owner).get("/api/notifications")

    assert response.status_code == 200
    (notice,) = [row for row in response.data["results"] if row["kind"] == "lot_discarded"]
    assert notice["lot"]["code"] == estate.evaluated.code


def test_a_failure_leaves_no_discard_and_no_notice(
    auth_client, estate, monkeypatch, django_capture_on_commit_callbacks
):
    def broken(self, *args, **kwargs):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(type(estate.evaluated), "advance_status", broken)
    client = auth_client(estate.inspector)
    client.raise_request_exception = False

    with django_capture_on_commit_callbacks(execute=True):
        response = discard(client, estate.evaluated)

    assert response.status_code == 500
    assert not LotDiscard.objects.filter(lot=estate.evaluated).exists()
    assert not QualityAuditEvent.objects.filter(lot=estate.evaluated).exists()
    assert notified(estate.evaluated) == set()
