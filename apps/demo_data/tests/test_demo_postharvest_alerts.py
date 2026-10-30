"""Los avisos de poscosecha en La Esperanza: lo que deja la semilla y la demostración del
sobresecado por la API.

Llama a la semilla directamente y no al comando, para que corra también en Windows. Los avisos de
desvío se crean al confirmarse cada registro: por eso la semilla corre con los `on_commit` activos.
"""

import uuid

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.activities.state import today_in_bogota
from apps.demo_data.catalog import (
    DEMO_FOREMAN_EMAIL,
    DEMO_PRODUCER_EMAIL,
    DEVIATIONS_BOX,
    LIVE_LOG_DRYER,
    NEAR_TARGET_DRYER,
    REMINDER_BOX,
)
from apps.demo_data.seed import seed_demo_data
from apps.drying.models import DryingLogEntry, DryingProcess
from apps.fermentation.models import FermentationProcess, FermentationTurn
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def seed(capture):
    with capture(execute=True):
        seed_demo_data()


@pytest.fixture
def seeded(django_capture_on_commit_callbacks):
    seed(django_capture_on_commit_callbacks)


@pytest.fixture
def owner(seeded):
    return User.objects.get(email=DEMO_PRODUCER_EMAIL)


@pytest.fixture
def foreman(seeded):
    return User.objects.get(email=DEMO_FOREMAN_EMAIL)


def lot_in(facility_name, model):
    return model.objects.get(facility__name=facility_name, ended_at__isnull=True).lot


def kinds_of(user, lot):
    return set(Notification.objects.filter(recipient=user, lot=lot).values_list("kind", flat=True))


def test_the_responsible_is_reminded_of_the_first_turn(foreman):
    lot = lot_in(REMINDER_BOX, FermentationProcess)

    assert kinds_of(foreman, lot) == {"fermentation_first_turn_due"}


def test_the_fermenting_lot_has_its_turn_pending(owner):
    lot = lot_in("C-02", FermentationProcess)

    assert kinds_of(owner, lot) == {"fermentation_turn_due"}


def test_the_off_range_lot_warns_of_its_temperature_and_its_ph(owner):
    lot = lot_in(DEVIATIONS_BOX, FermentationProcess)

    assert kinds_of(owner, lot) == {"fermentation_temperature_low", "fermentation_ph_high"}


def test_the_lot_near_its_target_says_so_and_has_its_log_pending(owner):
    lot = lot_in(NEAR_TARGET_DRYER, DryingProcess)

    assert kinds_of(owner, lot) == {"drying_near_target", "drying_log_due"}


def test_the_lot_for_the_live_log_has_its_log_pending_and_no_log_today(owner):
    process = DryingProcess.objects.get(facility__name=LIVE_LOG_DRYER, ended_at__isnull=True)

    assert kinds_of(owner, process.lot) == {"drying_log_due"}
    assert not process.logs.filter(log_date=today_in_bogota()).exists()


def test_running_it_again_adds_no_lot_turn_or_log(seeded, django_capture_on_commit_callbacks):
    before = (
        FermentationProcess.objects.count(),
        FermentationTurn.objects.count(),
        DryingProcess.objects.count(),
        DryingLogEntry.objects.count(),
        Notification.objects.count(),
    )

    seed(django_capture_on_commit_callbacks)

    after = (
        FermentationProcess.objects.count(),
        FermentationTurn.objects.count(),
        DryingProcess.objects.count(),
        DryingLogEntry.objects.count(),
        Notification.objects.count(),
    )
    assert after == before


def log_body(moisture):
    # Sin sol: hoy solo cuenta hasta ahora, y la prueba puede correr de madrugada.
    return {
        "id": str(uuid.uuid4()),
        "measured_at": timezone.now().isoformat(),
        "moisture_pct": moisture,
        "sun_hours": "0.0",
        "turn_count": 0,
        "weather": "cloudy",
    }


def test_the_live_overdrying_is_seen_on_saving_and_first_in_the_producer_inbox(
    foreman, owner, auth_client, django_capture_on_commit_callbacks
):
    lot = DryingProcess.objects.get(facility__name=LIVE_LOG_DRYER, ended_at__isnull=True).lot

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(foreman).post(
            f"/api/drying/{lot.pk}/logs", log_body("5.8"), format="json"
        )

    assert response.status_code == 201, response.data
    assert "drying_overdried" in {alert["kind"] for alert in response.data["alerts"]}
    first = auth_client(owner).get("/api/notifications").data["results"][0]
    assert (first["kind"], first["severity"]) == ("drying_overdried", "critical")
    assert first["lot"]["id"] == str(lot.pk)


def test_the_seed_leaves_the_live_log_ready_again(
    foreman, auth_client, django_capture_on_commit_callbacks
):
    lot = DryingProcess.objects.get(facility__name=LIVE_LOG_DRYER, ended_at__isnull=True).lot
    logged = auth_client(foreman).post(
        f"/api/drying/{lot.pk}/logs", log_body("5.8"), format="json"
    )
    assert logged.status_code == 201, logged.data

    seed(django_capture_on_commit_callbacks)

    assert not DryingLogEntry.objects.filter(pk=logged.data["id"]).exists()
