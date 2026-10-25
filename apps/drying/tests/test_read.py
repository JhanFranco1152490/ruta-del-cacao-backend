"""Consultar secados: la pantalla de trabajo y la ficha."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.drying.rules import day_number
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.postharvest_parameters.tests.factories import PostharvestParametersFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import DryingLogEntryFactory, DryingProcessFactory

pytestmark = pytest.mark.django_db

LOGS = "drying.log_drying"
URL = "/api/drying"


class Estate:
    """Un productor con dos fincas (F01 y F02). En F01, un lote en secado desde hace 52 horas,
    con la bitácora del día 1 y del 3 (el 2 sin bitácora), y uno ya seco; en F02, uno en secado.
    El productor ajustó su humedad meta."""

    def __init__(self):
        self.producer = ProducerFactory(member_code="PROD-000123")
        self.farm_a = FarmFactory(producer=self.producer, number=1)
        self.farm_b = FarmFactory(producer=self.producer, number=2)
        self.plot_a = characterized_plot(farm=self.farm_a, area_hectares=Decimal("5.00"))
        self.plot_b = characterized_plot(farm=self.farm_b, area_hectares=Decimal("5.00"))
        self.dryer_a = PostharvestFacilityFactory(
            farm=self.farm_a, name="M-01", facility_type="solar_dryer", capacity_kg=800
        )
        self.running = DryingProcessFactory(
            lot=self.lot(self.plot_a, LotStatus.DRYING),
            facility=self.dryer_a,
            started_at=timezone.now() - timedelta(hours=52),
        )
        # Llegan fuera de orden, como desde la cola sin conexión.
        self.third_day = DryingLogEntryFactory(process=self.running, day=3)
        self.first_day = DryingLogEntryFactory(
            process=self.running,
            day=1,
            sun_hours=Decimal("0.0"),
            weather="rainy",
            turn_count=0,
            turn_frequency_hours=None,
            shade_hours=Decimal("6.0"),
        )
        self.finished = DryingProcessFactory(
            lot=self.lot(self.plot_a, LotStatus.DRIED),
            facility=PostharvestFacilityFactory(
                farm=self.farm_a, name="M-90", facility_type="solar_dryer"
            ),
            started_at=timezone.now() - timedelta(days=8),
        )
        self.finished.ended_at = self.finished.started_at + timedelta(hours=116)
        self.finished.final_moisture_pct = Decimal("7.0")
        self.finished.dry_weight_kg = Decimal("313.2")
        self.finished.yield_pct = Decimal("38.2")
        self.finished.total_sun_hours = Decimal("31.5")
        self.finished.save()
        DryingLogEntryFactory(process=self.finished)
        self.elsewhere = DryingProcessFactory(
            lot=self.lot(self.plot_b, LotStatus.DRYING),
            facility=PostharvestFacilityFactory(
                farm=self.farm_b, name="M-91", facility_type="solar_dryer"
            ),
        )
        PostharvestParametersFactory(
            producer=self.producer,
            target_moisture_min_pct=Decimal("6.8"),
            target_moisture_max_pct=Decimal("7.2"),
            estimated_days_max=8,
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


def test_the_list_has_the_dryings_in_progress_oldest_first(auth_client, estate):
    response = auth_client(estate.owner).get(URL)

    assert lot_ids(response) == [str(estate.running.pk), str(estate.elsewhere.pk)]


def test_a_drying_shows_its_lot_dryer_responsible_and_logs_by_time(auth_client, estate):
    item = auth_client(estate.owner).get(URL).data["results"][0]

    assert item["lot"]["status"] == "drying"
    assert item["lot"]["harvest"]["plot"]["farm"]["code"] == "F01"
    assert item["lot"]["green_weight_kg"] == str(estate.running.lot.harvest.green_weight_kg)
    assert item["farm"] == {"id": str(estate.farm_a.pk), "code": "F01", "name": estate.farm_a.name}
    assert item["facility"] == {
        "id": str(estate.dryer_a.pk),
        "name": "M-01",
        "capacity_kg": "800.0",
    }
    assert item["responsible"]["id"] == str(estate.running.responsible.pk)
    assert (item["entry_moisture_pct"], item["entry_moisture_out_of_range"]) == ("58.0", False)
    assert [(log["day_number"], log["id"]) for log in item["logs"]] == [
        (1, str(estate.first_day.pk)),
        (3, str(estate.third_day.pk)),
    ]
    rainy = item["logs"][0]
    assert (rainy["sun_hours"], rainy["shade_hours"], rainy["weather"]) == ("0.0", "6.0", "rainy")
    assert rainy["turn_frequency_hours"] is None
    assert rainy["log_date"] == timezone.localdate(estate.first_day.measured_at).isoformat()
    # El día depende de la hora en que corre la prueba: se calcula con la misma regla.
    assert item["current_day"] == day_number(timezone.localdate(), estate.running.started_at)
    assert Decimal("52.0") <= Decimal(item["elapsed_hours"]) <= Decimal("52.1")
    assert item["result"] is None


def test_the_targets_are_the_producer_s_own_parameters(auth_client, estate):
    item = auth_client(estate.owner).get(URL).data["results"][0]

    assert item["target_moisture"] == {"min": "6.8", "max": "7.2"}
    assert item["estimated_days"] == {"min": 5, "max": 8}


def test_a_producer_without_parameters_sees_the_baseline_targets(auth_client):
    process = DryingProcessFactory()
    owner = make_producer_owner(process.lot.harvest.plot.farm.producer)

    item = auth_client(owner).get(f"{URL}/{process.pk}").data

    assert item["target_moisture"] == {"min": "6.5", "max": "7.5"}
    assert item["estimated_days"] == {"min": 5, "max": 7}


def test_a_finished_drying_shows_its_result(auth_client, estate):
    item = auth_client(estate.owner).get(f"{URL}/{estate.finished.pk}").data

    assert item["lot"]["status"] == "dried"
    assert item["result"] == {
        "ended_at": timezone.localtime(estate.finished.ended_at).isoformat(),
        "duration_hours": "116.0",
        "days": day_number(
            timezone.localdate(estate.finished.ended_at), estate.finished.started_at
        ),
        "total_sun_hours": "31.5",
        "final_moisture_pct": "7.0",
        "dry_weight_kg": "313.2",
        "yield_pct": "38.2",
    }
    assert item["elapsed_hours"] == "116.0"


def test_the_list_filters_by_farm(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"farm": estate.farm_b.pk})

    assert lot_ids(response) == [str(estate.elsewhere.pk)]


def test_the_foreman_sees_only_the_dryings_of_its_farm(auth_client, estate):
    client = auth_client(estate.foreman)

    assert lot_ids(client.get(URL)) == [str(estate.running.pk)]
    assert client.get(f"{URL}/{estate.elsewhere.pk}").status_code == 404


def test_the_list_needs_the_log_permission(auth_client, estate):
    viewer = make_delegate(estate.producer, ["lots.view_lot"], farm=estate.farm_a)
    logger = make_delegate(estate.producer, [LOGS], farm=estate.farm_a)

    assert auth_client(viewer).get(URL).status_code == 403
    assert auth_client(logger).get(URL).status_code == 200


def test_whoever_sees_the_lot_sees_its_drying(auth_client, estate):
    viewer = make_delegate(estate.producer, ["lots.view_lot"], farm=estate.farm_a)

    assert auth_client(viewer).get(f"{URL}/{estate.running.pk}").status_code == 200


def test_a_lot_without_drying_is_not_found(auth_client, estate):
    lot = LotFactory(harvest=HarvestFactory(plot=estate.plot_a), status=LotStatus.FERMENTED)

    response = auth_client(estate.owner).get(f"{URL}/{lot.pk}")

    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_the_drying_of_another_producer_is_not_found(auth_client, estate):
    other = DryingProcessFactory()

    assert auth_client(estate.owner).get(f"{URL}/{other.pk}").status_code == 404
    assert str(other.pk) not in lot_ids(auth_client(estate.owner).get(URL))


def test_the_technical_account_filters_by_producer(auth_client, estate):
    other = DryingProcessFactory()
    client = auth_client(UserFactory(is_superuser=True))

    everyone = lot_ids(client.get(URL))
    only_one = lot_ids(client.get(URL, {"producer": other.lot.harvest.plot.farm.producer_id}))

    assert {str(estate.running.pk), str(other.pk)} <= set(everyone)
    assert only_one == [str(other.pk)]


def test_the_list_does_not_grow_its_queries_with_more_dryings(auth_client, estate):
    client = auth_client(estate.owner)
    with CaptureQueriesContext(connection) as few:
        client.get(URL)
    for number in range(5):
        process = DryingProcessFactory(
            lot=estate.lot(estate.plot_a, LotStatus.DRYING),
            facility=PostharvestFacilityFactory(
                farm=estate.farm_a, name=f"M-6{number}", facility_type="solar_dryer"
            ),
        )
        DryingLogEntryFactory(process=process)

    with CaptureQueriesContext(connection) as many:
        response = client.get(URL)

    assert len(response.data["results"]) == 7
    assert len(many) == len(few)
