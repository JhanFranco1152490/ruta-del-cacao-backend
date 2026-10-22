"""Las tres demostraciones del sprint, hechas por la API contra los datos sembrados: si la semilla
deja de tener lo que cada demostración necesita (el monitoreo programado, la variedad sembrada, el
nombre libre del cajón), una de estas pruebas falla."""

import re
import uuid
from datetime import timedelta

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.accounts.tests.helpers import login_by_email
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity
from apps.activities.state import today_in_bogota
from apps.demo_data.catalog import (
    DEMO_FARM,
    DEMO_FOREMAN_EMAIL,
    DEMO_OPERATOR_EMAIL,
    DEMO_PASSWORD,
    DEMO_PLOT,
    DEMO_PRODUCER_EMAIL,
    LIVE_FACILITY_NAME,
)
from apps.facilities.models import PostharvestFacility
from apps.harvests.models import Harvest
from apps.health.models import Detection, PestDisease
from apps.lots.models import Lot

pytestmark = pytest.mark.django_db

LOT_CODE = re.compile(r"^\d{6}-F\d{2}-P\d{2}-\d{6}-\d+$")


def seed():
    call_command("seed_demo_data", stdout=open("/dev/null", "w"))


@pytest.fixture
def seeded():
    seed()


@pytest.fixture
def foreman(seeded):
    return User.objects.get(email=DEMO_FOREMAN_EMAIL)


@pytest.fixture
def owner(seeded):
    return User.objects.get(email=DEMO_PRODUCER_EMAIL)


def the_monitoring():
    return AgriculturalActivity.objects.get(
        plot__farm__name=DEMO_FARM,
        plot__name=DEMO_PLOT,
        activity_type=ActivityType.PHYTOSANITARY_MONITORING,
        status=ActivityStatus.SCHEDULED,
    )


def monitoring_body(affected, **extra):
    monilia = PestDisease.objects.get(name="Monilia")
    return {
        "done_date": str(today_in_bogota()),
        "sampling_unit": "trees",
        "evaluated_units": 50,
        "sampling_method": "zigzag",
        "notes": "",
        "no_presence": False,
        "captured_at": "2026-10-22T15:00:00Z",
        "detections": [
            {
                "id": str(uuid.uuid4()),
                "pest_disease_id": str(monilia.pk),
                "other_description": None,
                "affected_units": affected,
                **extra,
            }
        ],
    }


def test_each_demo_account_signs_in_with_the_public_password(seeded, api_client):
    for email in (DEMO_FOREMAN_EMAIL, DEMO_OPERATOR_EMAIL):
        assert login_by_email(api_client, email, DEMO_PASSWORD).status_code == 200


def test_the_foreman_and_the_operator_only_reach_their_own_farm(seeded, auth_client):
    seen = {}
    for email in (DEMO_FOREMAN_EMAIL, DEMO_OPERATOR_EMAIL):
        response = auth_client(User.objects.get(email=email)).get("/api/farms")
        seen[email] = [farm["name"] for farm in response.data["results"]]

    assert seen == {DEMO_FOREMAN_EMAIL: ["La Esperanza"], DEMO_OPERATOR_EMAIL: ["El Mirador"]}


def test_running_it_again_adds_nothing_but_a_fresh_monitoring_for_today(seeded):
    def counts():
        return (
            AgriculturalActivity.objects.count(),
            Harvest.objects.count(),
            Lot.objects.count(),
            PostharvestFacility.objects.count(),
            User.objects.count(),
        )

    before = counts()
    seed()

    assert counts() == before


def test_the_monitoring_for_today_comes_back_once_it_has_been_recorded(
    seeded, foreman, auth_client
):
    monitoring = the_monitoring()
    response = auth_client(foreman).post(
        f"/api/agricultural-activities/{monitoring.pk}/monitoring",
        monitoring_body(10),
        format="json",
    )
    assert response.status_code == 201

    seed()

    assert the_monitoring().pk != monitoring.pk


def test_demo_1_the_monitoring_gives_20_percent_and_a_scheduled_control(foreman, auth_client):
    client = auth_client(foreman)
    monitoring = the_monitoring()
    assert (monitoring.assignee, monitoring.scheduled_date) == (foreman, today_in_bogota())
    url = f"/api/agricultural-activities/{monitoring.pk}/monitoring"

    wrong = client.post(url, monitoring_body(60), format="json")

    assert wrong.status_code in (400, 422)
    assert any("50" in message for message in wrong.data["fields"]["detections"])
    monitoring.refresh_from_db()
    assert monitoring.status == ActivityStatus.SCHEDULED

    control_day = today_in_bogota() + timedelta(days=3)
    control = {
        "id": str(uuid.uuid4()),
        "mode": "scheduled",
        "scheduled_date": str(control_day),
        "assignee_id": str(foreman.pk),
        "method": None,
        "planned_input_id": None,
    }
    right = client.post(url, monitoring_body(10, control=control), format="json")

    assert right.status_code == 201
    assert right.data["status"] == ActivityStatus.DONE
    detection = Detection.objects.get(monitoring__activity=monitoring)
    assert str(detection.incidence) == "20.00"
    listed = client.get(
        "/api/agricultural-activities",
        {"from": str(today_in_bogota()), "to": str(control_day)},
    )
    controls = [
        row
        for row in listed.data["results"]
        if row["activity_type"] == ActivityType.PHYTOSANITARY_CONTROL
        and row["scheduled_date"] == str(control_day)
    ]
    assert [row["state"] for row in controls] == ["scheduled"]


def test_the_second_monitoring_of_today_stays_for_the_wrong_value(foreman, auth_client):
    other = AgriculturalActivity.objects.get(
        plot__farm__name=DEMO_FARM,
        plot__name="L-02",
        activity_type=ActivityType.PHYTOSANITARY_MONITORING,
        status=ActivityStatus.SCHEDULED,
        scheduled_date=today_in_bogota(),
    )

    wrong = auth_client(foreman).post(
        f"/api/agricultural-activities/{other.pk}/monitoring",
        monitoring_body(60),
        format="json",
    )

    assert wrong.status_code in (400, 422)
    other.refresh_from_db()
    assert other.status == ActivityStatus.SCHEDULED


def test_demo_2_the_harvest_becomes_a_lot_and_zero_kilos_are_refused(foreman, owner, auth_client):
    client = auth_client(foreman)
    monitoring = the_monitoring()
    plot = monitoring.plot
    variety = plot.characterization.plantings.order_by("planting_date").first().variety
    body = {
        "plot_id": str(plot.pk),
        "harvest_date": str(today_in_bogota()),
        "green_weight_kg": "120",
        "variety_id": str(variety.pk),
        "collector_id": str(foreman.pk),
    }

    created = client.post("/api/harvests", body, format="json")

    assert created.status_code == 201
    harvest = Harvest.objects.get(pk=created.data["id"])
    assert harvest.plot == plot
    listed = auth_client(owner).get(
        "/api/harvests", {"from": str(today_in_bogota()), "to": str(today_in_bogota())}
    )
    assert str(harvest.pk) in [row["id"] for row in listed.data["results"]]

    lot = client.post("/api/lots", {"harvest_id": str(harvest.pk)}, format="json")

    assert lot.status_code == 201
    assert LOT_CODE.match(lot.data["code"])

    zero = client.post("/api/harvests", {**body, "green_weight_kg": "0"}, format="json")

    assert zero.status_code in (400, 422)
    assert "green_weight_kg" in zero.data["fields"]


def test_demo_3_the_facility_is_registered_once_and_then_deactivated(owner, auth_client):
    client = auth_client(owner)
    farm = owner.producer.farms.get(name=DEMO_FARM)
    body = {
        "farm_id": str(farm.pk),
        "facility_type": "fermentation_box",
        "name": LIVE_FACILITY_NAME,
        "capacity_kg": 500,
    }

    created = client.post("/api/postharvest-facilities", body, format="json")

    assert created.status_code == 201
    assert created.data["status"] == "available"

    again = client.post("/api/postharvest-facilities", body, format="json")

    assert (again.status_code, again.data["code"]) == (409, "duplicate_facility_name")

    off = client.patch(
        f"/api/postharvest-facilities/{created.data['id']}",
        {"expected_version": created.data["version"], "is_active": False},
        format="json",
    )

    assert off.status_code == 200
    assert off.data["status"] == "inactive"
    assert PostharvestFacility.objects.get(pk=created.data["id"]).audit_events.count() == 2


def test_the_live_facility_name_is_freed_when_the_seed_runs_again(owner, auth_client):
    client = auth_client(owner)
    farm = owner.producer.farms.get(name=DEMO_FARM)
    client.post(
        "/api/postharvest-facilities",
        {
            "farm_id": str(farm.pk),
            "facility_type": "fermentation_box",
            "name": LIVE_FACILITY_NAME,
            "capacity_kg": 500,
        },
        format="json",
    )

    seed()

    assert not PostharvestFacility.objects.filter(name=LIVE_FACILITY_NAME).exists()
