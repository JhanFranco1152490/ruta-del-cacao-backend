"""Corregir el inicio de un secado mientras no tenga bitácora."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.drying.models import DryingProcess, DryingProcessAuditEvent

from .factories import DryingLogEntryFactory
from .helpers import Farmstead

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Farmstead()


@pytest.fixture
def client(auth_client, estate):
    return auth_client(estate.owner)


@pytest.fixture
def started(client, estate):
    response = client.post("/api/drying", estate.start_body(), format="json")
    assert response.status_code == 201, response.data
    return response.data


def correct(client, estate, version, **changes):
    return client.patch(
        f"/api/drying/{estate.lot.pk}", {"expected_version": version, **changes}, format="json"
    )


def test_changing_the_dryer_frees_the_old_one_and_takes_the_new_one(client, estate, started):
    response = correct(client, estate, started["version"], facility_id=str(estate.other_dryer.pk))

    assert response.status_code == 200, response.data
    assert response.data["facility"]["name"] == "M-02"
    assert response.data["version"] == started["version"] + 1
    estate.dryer.refresh_from_db()
    estate.other_dryer.refresh_from_db()
    assert estate.dryer.current_lot_id is None
    assert estate.other_dryer.current_lot_id == estate.lot.pk
    event = DryingProcessAuditEvent.objects.get(process_id=estate.lot.pk, action="updated")
    assert set(event.changes) == {"facility_id"}


def test_the_moisture_the_time_and_the_responsible_are_corrected(client, estate, started):
    earlier = (timezone.now() - timedelta(hours=3)).isoformat()

    response = correct(
        client,
        estate,
        started["version"],
        entry_moisture_pct="57.5",
        started_at=earlier,
        responsible_id=str(estate.owner.pk),
    )

    assert response.status_code == 200, response.data
    assert response.data["entry_moisture_pct"] == "57.5"
    assert response.data["responsible"]["id"] == str(estate.owner.pk)


def test_a_corrected_moisture_out_of_range_asks_for_confirmation(client, estate, started):
    refused = correct(client, estate, started["version"], entry_moisture_pct="85.0")

    assert (refused.status_code, refused.data["code"]) == (422, "entry_moisture_out_of_range")

    confirmed = correct(
        client, estate, started["version"], entry_moisture_pct="85.0", confirm_entry_moisture=True
    )

    assert confirmed.data["entry_moisture_out_of_range"] is True


def test_a_correction_without_real_changes_keeps_the_version(client, estate, started):
    response = correct(client, estate, started["version"], entry_moisture_pct="58.0")

    assert response.data["version"] == started["version"]
    assert not DryingProcessAuditEvent.objects.filter(action="updated").exists()


def test_a_stale_version_is_refused_with_the_current_drying(client, estate, started):
    response = correct(client, estate, started["version"] + 5, entry_moisture_pct="57.0")

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["version"] == started["version"]


def test_with_a_log_the_start_is_no_longer_corrected(client, estate, started):
    DryingLogEntryFactory(process=DryingProcess.objects.get(pk=estate.lot.pk))

    response = correct(client, estate, started["version"], entry_moisture_pct="57.0")

    assert (response.status_code, response.data["code"]) == (409, "drying_has_logs")


def test_the_correction_needs_a_version_and_some_change(client, estate, started):
    assert (
        client.patch(
            f"/api/drying/{estate.lot.pk}", {"entry_moisture_pct": "57.0"}, format="json"
        ).status_code
        == 400
    )
    assert correct(client, estate, started["version"]).status_code == 400


def test_the_options_of_a_drying_without_logs_include_its_dryer(client, estate, started):
    response = client.get("/api/drying/start-options", {"lot": estate.lot.pk})

    assert response.status_code == 200, response.data
    assert [dryer["name"] for dryer in response.data["facilities"]] == ["M-01", "M-02"]
