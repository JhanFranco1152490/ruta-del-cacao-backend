"""El secado en La Esperanza: lo que deja la semilla y la demostración por la API.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

import uuid

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.demo_data.catalog import DEMO_FARM, DEMO_FOREMAN_EMAIL, DEMO_PRODUCER_EMAIL
from apps.demo_data.seed import seed_demo_data
from apps.drying.models import DryingLogEntry, DryingProcess
from apps.facilities.models import PostharvestFacility
from apps.lots.choices import LotStatus
from apps.lots.models import Lot

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    seed_demo_data()


def demo_lots(status):
    return Lot.objects.filter(harvest__plot__farm__name=DEMO_FARM, status=status)


def test_the_seed_leaves_a_dried_lot_one_drying_and_one_ready(seeded):
    done = DryingProcess.objects.get(lot__status=LotStatus.DRIED)
    running = DryingProcess.objects.get(lot__status=LotStatus.DRYING)

    assert done.yield_pct is not None and done.dry_weight_kg is not None
    assert done.facility.current_lot_id is None
    assert done.logs.count() == 5
    assert running.facility.current_lot_id == running.pk
    days = list(running.logs.order_by("day_number").values_list("day_number", "weather"))
    assert days == [(1, "sunny"), (2, "rainy")]
    assert not running.logs.filter(log_date=timezone.localdate()).exists()
    assert demo_lots(LotStatus.FERMENTED).exists()


def test_a_dryer_is_free_for_the_live_demonstration(seeded):
    free = PostharvestFacility.objects.filter(
        farm__name=DEMO_FARM, facility_type="solar_dryer", current_lot__isnull=True
    )

    assert free.exists()


def test_running_it_again_adds_no_drying(seeded):
    before = (DryingProcess.objects.count(), DryingLogEntry.objects.count())

    seed_demo_data()

    assert (DryingProcess.objects.count(), DryingLogEntry.objects.count()) == before


def test_the_demonstration_starts_logs_and_finishes_a_drying(seeded, auth_client):
    foreman = User.objects.get(email=DEMO_FOREMAN_EMAIL)
    owner = User.objects.get(email=DEMO_PRODUCER_EMAIL)
    lot = demo_lots(LotStatus.FERMENTED).first()
    client = auth_client(foreman)

    options = client.get("/api/drying/start-options", {"lot": str(lot.pk)}).data
    started = client.post(
        "/api/drying",
        {
            "lot_id": str(lot.pk),
            "facility_id": options["facilities"][0]["id"],
            "started_at": timezone.now().isoformat(),
            "entry_moisture_pct": "58.0",
            "responsible_id": str(foreman.pk),
        },
        format="json",
    )
    assert started.status_code == 201, started.data

    # La bitácora de hoy del lote que ya estaba secando. Sin sol: hoy solo cuenta hasta ahora, y la
    # prueba puede correr de madrugada.
    running = DryingProcess.objects.filter(lot__status=LotStatus.DRYING).exclude(pk=lot.pk).get()
    body = {
        "id": str(uuid.uuid4()),
        "measured_at": timezone.now().isoformat(),
        "moisture_pct": "39.5",
        "sun_hours": "0.0",
        "turn_count": 0,
        "weather": "cloudy",
    }
    logged = client.post(f"/api/drying/{running.pk}/logs", body, format="json")
    assert logged.status_code == 201, logged.data

    repeated = client.post(
        f"/api/drying/{running.pk}/logs", {**body, "id": str(uuid.uuid4())}, format="json"
    )
    assert (repeated.status_code, repeated.data["code"]) == (409, "duplicate_drying_log_date")

    version = client.get(f"/api/drying/{running.pk}").data["version"]
    green = running.lot.harvest.green_weight_kg
    finish = {
        "expected_version": version,
        "ended_at": timezone.now().isoformat(),
        "final_moisture_pct": "7.0",
    }
    owner_client = auth_client(owner)
    too_heavy = owner_client.post(
        f"/api/drying/{running.pk}/finish",
        {**finish, "dry_weight_kg": str(green + 1)},
        format="json",
    )
    assert too_heavy.status_code == 400

    finished = owner_client.post(
        f"/api/drying/{running.pk}/finish", {**finish, "dry_weight_kg": "95.0"}, format="json"
    )
    assert finished.status_code == 200, finished.data
    assert finished.data["lot"]["status"] == "dried"
    assert finished.data["result"]["yield_pct"] == "38.0"
