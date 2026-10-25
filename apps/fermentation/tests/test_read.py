"""Consultar fermentaciones: la pantalla de trabajo, la ficha y lo que pide el formulario."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.facilities.models import PostharvestFacility
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import FermentationProcessFactory, FermentationTurnFactory

pytestmark = pytest.mark.django_db

MANAGE = "fermentation.manage_fermentation"
TURNS = "fermentation.log_turns"


class Estate:
    """Un productor con dos fincas (F01 y F02). En F01, un lote recién conformado, uno en
    fermentación con dos volteos y uno ya fermentado; en F02, uno en fermentación."""

    def __init__(self):
        self.producer = ProducerFactory(member_code="PROD-000123")
        self.farm_a = FarmFactory(producer=self.producer, number=1)
        self.farm_b = FarmFactory(producer=self.producer, number=2)
        self.plot_a = characterized_plot(farm=self.farm_a, area_hectares=Decimal("5.00"))
        self.plot_b = characterized_plot(farm=self.farm_b, area_hectares=Decimal("5.00"))
        self.box_a = PostharvestFacilityFactory(farm=self.farm_a, name="C-01")
        self.new_lot = self.lot(self.plot_a, LotStatus.GENERATED)
        self.running = FermentationProcessFactory(
            lot=self.lot(self.plot_a, LotStatus.FERMENTING), facility=self.box_a
        )
        start = self.running.started_at.replace(second=0, microsecond=0)
        # Llegan fuera de orden, como desde la cola sin conexión.
        self.second_turn = FermentationTurnFactory(
            process=self.running, turned_at=start + timedelta(hours=49)
        )
        self.first_turn = FermentationTurnFactory(
            process=self.running, turned_at=start + timedelta(hours=24)
        )
        self.finished = FermentationProcessFactory(
            lot=self.lot(self.plot_a, LotStatus.FERMENTED),
            facility=PostharvestFacilityFactory(farm=self.farm_a, name="C-90"),
            started_at=timezone.now() - timedelta(days=8),
        )
        self.finished.ended_at = self.finished.started_at + timedelta(hours=122)
        self.finished.end_notes = "Buen olor al corte."
        self.finished.save()
        FermentationTurnFactory(process=self.finished)
        self.elsewhere = FermentationProcessFactory(
            lot=self.lot(self.plot_b, LotStatus.FERMENTING),
            facility=PostharvestFacilityFactory(farm=self.farm_b, name="C-91"),
        )
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm_a), get_system_role(FOREMAN)
        )

    def lot(self, plot, status):
        return LotFactory(harvest=HarvestFactory(plot=plot), status=status)


@pytest.fixture
def estate():
    return Estate()


def lot_ids(response):
    assert response.status_code == 200, response.data
    return [item["lot"]["id"] for item in response.data["results"]]


def occupy(facility, process):
    facility.current_lot = process.lot
    facility.occupied_since = process.started_at
    facility.save()


def test_the_list_has_the_fermentations_in_progress_oldest_first(auth_client, estate):
    response = auth_client(estate.owner).get("/api/fermentation")

    assert lot_ids(response) == [str(estate.running.pk), str(estate.elsewhere.pk)]


def test_a_fermentation_shows_its_lot_box_responsible_and_numbered_turns(auth_client, estate):
    item = auth_client(estate.owner).get("/api/fermentation").data["results"][0]

    assert item["lot"]["status"] == "fermenting"
    assert item["lot"]["harvest"]["plot"]["farm"]["code"] == "F01"
    assert item["lot"]["green_weight_kg"] == str(estate.running.lot.harvest.green_weight_kg)
    assert item["farm"] == {"id": str(estate.farm_a.pk), "code": "F01", "name": estate.farm_a.name}
    assert item["facility"] == {"id": str(estate.box_a.pk), "name": "C-01", "capacity_kg": "600.0"}
    assert item["responsible"]["id"] == str(estate.running.responsible.pk)
    assert item["over_capacity"] is False
    assert [(turn["number"], turn["id"]) for turn in item["turns"]] == [
        (1, str(estate.first_turn.pk)),
        (2, str(estate.second_turn.pk)),
    ]
    first = item["turns"][0]
    assert (first["temperature_c"], first["ph"]) == ("45.0", "4.90")
    assert first["hours_since_start"] == "24.0"
    assert Decimal("52.0") <= Decimal(item["elapsed_hours"]) <= Decimal("52.1")
    due = estate.second_turn.turned_at + timedelta(hours=24)
    assert item["next_turn_due_at"] == timezone.localtime(due).isoformat()
    assert item["result"] is None


def test_the_list_filters_by_farm(auth_client, estate):
    response = auth_client(estate.owner).get("/api/fermentation", {"farm": str(estate.farm_b.pk)})

    assert lot_ids(response) == [str(estate.elsewhere.pk)]


def test_the_foreman_only_reaches_the_fermentations_of_its_farm(auth_client, estate):
    client = auth_client(estate.foreman)

    assert lot_ids(client.get("/api/fermentation")) == [str(estate.running.pk)]
    response = client.get(f"/api/fermentation/{estate.elsewhere.pk}")
    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_the_technical_account_sees_all_and_filters_by_producer(auth_client, estate):
    client = auth_client(UserFactory(is_superuser=True))
    other = FermentationProcessFactory()
    producer = str(other.lot.harvest.plot.farm.producer_id)

    assert len(lot_ids(client.get("/api/fermentation"))) == 3
    assert lot_ids(client.get("/api/fermentation", {"producer": producer})) == [str(other.pk)]


def test_the_list_needs_the_turns_permission_and_the_detail_only_seeing_the_lot(
    auth_client, estate
):
    client = auth_client(make_delegate(estate.producer, ["lots.view_lot"], farm=estate.farm_a))

    assert client.get("/api/fermentation").status_code == 403
    assert client.get(f"/api/fermentation/{estate.running.pk}").status_code == 200


def test_a_finished_fermentation_shows_its_result(auth_client, estate):
    response = auth_client(estate.owner).get(f"/api/fermentation/{estate.finished.pk}")

    assert response.status_code == 200
    assert response.data["result"] == {
        "ended_at": timezone.localtime(estate.finished.ended_at).isoformat(),
        "duration_hours": "122.0",
        "turn_count": 1,
        "notes": "Buen olor al corte.",
    }
    assert response.data["elapsed_hours"] == "122.0"
    assert response.data["next_turn_due_at"] is None


def test_a_lot_without_fermentation_has_no_detail(auth_client, estate):
    response = auth_client(estate.owner).get(f"/api/fermentation/{estate.new_lot.pk}")

    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_the_list_query_count_does_not_grow_with_the_fermentations(auth_client, estate):
    client = auth_client(estate.owner)
    with CaptureQueriesContext(connection) as few:
        client.get("/api/fermentation")
    for number in range(5):
        process = FermentationProcessFactory(
            lot=estate.lot(estate.plot_a, LotStatus.FERMENTING),
            facility=PostharvestFacilityFactory(farm=estate.farm_a, name=f"C-5{number}"),
        )
        FermentationTurnFactory(process=process)

    with CaptureQueriesContext(connection) as many:
        response = client.get("/api/fermentation")

    assert len(response.data["results"]) == 7
    assert len(many) == len(few)


# --- Lo que pide el formulario de iniciar o corregir el inicio ---


def options(client, lot):
    return client.get("/api/fermentation/start-options", {"lot": str(lot.pk)})


def test_the_options_offer_the_free_boxes_of_the_lot_farm(auth_client, estate):
    free = PostharvestFacilityFactory(farm=estate.farm_a, name="C-02", capacity_kg=450)
    PostharvestFacilityFactory(farm=estate.farm_a, name="C-03", is_active=False)
    PostharvestFacilityFactory(
        farm=estate.farm_a,
        name="M-01",
        facility_type=PostharvestFacility.FacilityType.SOLAR_DRYER,
    )
    PostharvestFacilityFactory(farm=estate.farm_b, name="C-92")
    occupy(estate.box_a, estate.running)

    response = options(auth_client(estate.owner), estate.new_lot)

    assert response.status_code == 200
    # C-90 quedó libre al finalizar su fermentación.
    assert [
        (box["id"], box["name"], box["capacity_kg"]) for box in response.data["facilities"]
    ] == [
        (str(free.pk), "C-02", "450.0"),
        (str(estate.finished.facility.pk), "C-90", "600.0"),
    ]
    assert response.data["green_weight_kg"] == str(estate.new_lot.harvest.green_weight_kg)
    midnight = datetime.combine(estate.new_lot.harvest.harvest_date, time.min)
    assert response.data["earliest_start_at"] == timezone.make_aware(midnight).isoformat()


def test_correcting_the_start_also_offers_the_box_it_already_has(auth_client, estate):
    estate.first_turn.delete()
    estate.second_turn.delete()
    occupy(estate.box_a, estate.running)

    response = options(auth_client(estate.owner), estate.running.lot)

    assert [box["name"] for box in response.data["facilities"]] == ["C-01", "C-90"]


def test_the_options_offer_only_who_can_be_responsible_in_the_lot_farm(auth_client, estate):
    manager_b = make_delegate(estate.producer, [MANAGE], farm=estate.farm_b)
    turns_only = make_delegate(estate.producer, [TURNS], farm=estate.farm_a)
    inactive = make_delegate(estate.producer, [MANAGE], farm=estate.farm_a)
    inactive.is_active = False
    inactive.save()

    response = options(auth_client(estate.owner), estate.new_lot)

    offered = {person["id"] for person in response.data["responsibles"]}
    assert offered == {str(estate.owner.pk), str(estate.foreman.pk)}
    assert not offered & {str(manager_b.pk), str(turns_only.pk), str(inactive.pk)}
    assert all(person["assignable"] for person in response.data["responsibles"])


@pytest.mark.parametrize("which", ["running", "finished"])
def test_the_options_refuse_a_lot_that_cannot_start_or_be_corrected(auth_client, estate, which):
    lot = getattr(estate, which).lot

    response = options(auth_client(estate.owner), lot)

    assert (response.status_code, response.data["code"]) == (409, "lot_invalid_status")
    assert response.data["current_status"] == lot.status


def test_the_options_need_the_manage_permission_and_the_lot_in_reach(auth_client, estate):
    turns_only = make_delegate(estate.producer, [TURNS], farm=estate.farm_a)
    lot_b = estate.lot(estate.plot_b, LotStatus.GENERATED)

    assert options(auth_client(turns_only), estate.new_lot).status_code == 403
    assert options(auth_client(estate.foreman), lot_b).status_code == 404
    assert auth_client(estate.owner).get("/api/fermentation/start-options").status_code == 400


# --- Lo que la fermentación agrega a un lote ---


def test_a_lot_shows_its_fermentation(auth_client, estate):
    client = auth_client(estate.owner)

    detail = client.get(f"/api/lots/{estate.running.pk}").data
    fresh = client.get(f"/api/lots/{estate.new_lot.pk}").data

    assert detail["fermentation"] == {
        "started_at": timezone.localtime(estate.running.started_at).isoformat(),
        "ended_at": None,
        "facility": "C-01",
    }
    assert fresh["fermentation"] is None


def test_the_lot_list_shows_the_fermentation_without_more_queries(auth_client, estate):
    client = auth_client(estate.owner)
    with CaptureQueriesContext(connection) as few:
        client.get("/api/lots")
    for day in range(1, 6):
        harvest = HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 9, day))
        FermentationProcessFactory(
            lot=LotFactory(harvest=harvest, status=LotStatus.FERMENTING),
            facility=PostharvestFacilityFactory(farm=estate.farm_a, name=f"C-6{day}"),
        )

    with CaptureQueriesContext(connection) as many:
        response = client.get("/api/lots", {"page_size": 100})

    assert sum(1 for lot in response.data["results"] if lot["fermentation"]) == 8
    assert len(many) == len(few)
