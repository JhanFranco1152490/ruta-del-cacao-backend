"""La fermentación en La Esperanza: lo que deja la semilla y la demostración por la API.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

import uuid

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.demo_data.catalog import DEMO_FARM, DEMO_FOREMAN_EMAIL, DEMO_PRODUCER_EMAIL
from apps.demo_data.seed import seed_demo_data
from apps.facilities.models import PostharvestFacility
from apps.fermentation.alerts import next_turn_due_at
from apps.fermentation.models import FermentationProcess, FermentationTurn
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.postharvest_parameters.baseline import FERMENTATION_BASELINE

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    seed_demo_data()


def demo_lots(status):
    return Lot.objects.filter(harvest__plot__farm__name=DEMO_FARM, status=status)


def test_the_seed_leaves_a_lot_to_start_one_fermenting_and_one_fermented(seeded):
    ready = demo_lots(LotStatus.GENERATED)
    running = FermentationProcess.objects.get(lot__status=LotStatus.FERMENTING)
    done = FermentationProcess.objects.get(lot__status=LotStatus.FERMENTED)

    assert ready.exists()
    assert running.facility.current_lot_id == running.pk
    assert running.turns.count() == 2
    last = running.turns.order_by("-turned_at").first().turned_at
    assert next_turn_due_at(running.started_at, last, FERMENTATION_BASELINE) < timezone.now()
    assert done.ended_at is not None and done.turns.count() == 3
    assert done.facility.current_lot_id is None


def test_a_box_is_free_for_the_live_demonstration(seeded):
    free = PostharvestFacility.objects.filter(
        farm__name=DEMO_FARM, facility_type="fermentation_box", current_lot__isnull=True
    )

    assert free.exists()


def test_running_it_again_adds_no_fermentation(seeded):
    before = (FermentationProcess.objects.count(), FermentationTurn.objects.count())

    seed_demo_data()

    assert (FermentationProcess.objects.count(), FermentationTurn.objects.count()) == before


def test_the_demonstration_starts_turns_and_finishes_a_lot(seeded, auth_client):
    foreman = User.objects.get(email=DEMO_FOREMAN_EMAIL)
    owner = User.objects.get(email=DEMO_PRODUCER_EMAIL)
    lot = demo_lots(LotStatus.GENERATED).first()
    client = auth_client(foreman)

    options = client.get("/api/fermentation/start-options", {"lot": str(lot.pk)}).data
    box = options["facilities"][0]
    started = client.post(
        "/api/fermentation",
        {
            "lot_id": str(lot.pk),
            "facility_id": box["id"],
            "started_at": timezone.now().isoformat(),
            "responsible_id": str(foreman.pk),
        },
        format="json",
    )
    assert started.status_code == 201, started.data

    # El caso negativo: un pH que no existe no se guarda.
    turn = {"id": str(uuid.uuid4()), "turned_at": timezone.now().isoformat()}
    turn |= {"temperature_c": "38.5", "ph": "15.00"}
    refused = client.post(f"/api/fermentation/{lot.pk}/turns", turn, format="json")
    assert refused.status_code == 400
    assert refused.data["fields"]["ph"] == ["pH válido entre 0 y 14"]

    turn["ph"] = "5.10"
    assert client.post(f"/api/fermentation/{lot.pk}/turns", turn, format="json").status_code == 201

    finished = auth_client(owner).post(
        f"/api/fermentation/{lot.pk}/finish",
        {"expected_version": 1, "ended_at": timezone.now().isoformat()},
        format="json",
    )
    assert finished.status_code == 200, finished.data
    assert finished.data["lot"]["status"] == "fermented"
