import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.activities.state import today_in_bogota
from apps.farms.tests.factories import FarmFactory
from apps.health.tests.factories import (
    DetectionFactory,
    PestDiseaseFactory,
    PhytosanitaryMonitoringFactory,
    PhytosanitaryTreatmentFactory,
    done_monitoring,
)
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

URL = "/api/phytosanitary-detections/without-control"
COMPLETE = "activities.complete_agriculturalactivity"


@pytest.fixture
def farm():
    return FarmFactory(name="La Esperanza")


@pytest.fixture
def plot(farm):
    return PlotFactory(farm=farm)


@pytest.fixture
def owner(farm):
    return make_producer_owner(farm.producer)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


def detection_on(plot, done_on, **kwargs):
    monitoring = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot, done_date=done_on)
    )
    return DetectionFactory(monitoring=monitoring, **kwargs)


def listed(response) -> list[str]:
    assert response.status_code == 200
    return [row["id"] for row in response.json()["results"]]


def test_it_lists_the_detections_without_control_from_the_oldest(client, plot):
    monilia = PestDiseaseFactory(name="Monilia", kind="disease")
    new = detection_on(plot, date(2026, 10, 1), pest_disease=monilia, incidence=Decimal("24.00"))
    old = detection_on(plot, date(2026, 8, 1))

    response = client.get(URL)

    assert listed(response) == [str(old.pk), str(new.pk)]
    assert response.json()["results"][1] == {
        "id": str(new.pk),
        "pest_disease": {
            "id": str(monilia.pk),
            "name": "Monilia",
            "kind": "disease",
            "is_active": True,
        },
        "other_description": None,
        "affected_units": new.affected_units,
        "incidence": "24.00",
        "sampling_unit": "trees",
        "monitoring": {"id": str(new.monitoring.pk), "done_date": "2026-10-01"},
        "plot": {
            "id": str(plot.pk),
            "code": plot.code,
            "farm": {"id": str(plot.farm.pk), "name": "La Esperanza"},
        },
    }


def test_a_detection_leaves_the_list_once_it_has_a_control(client, plot):
    attended = detection_on(plot, date(2026, 10, 1))
    waiting = detection_on(plot, date(2026, 10, 2))
    PhytosanitaryTreatmentFactory(detection=attended)

    assert listed(client.get(URL)) == [str(waiting.pk)]


def test_programming_a_control_through_the_api_removes_it(client, plot, owner):
    waiting = detection_on(plot, today_in_bogota() - timedelta(days=1))

    client.post(
        f"/api/phytosanitary-detections/{waiting.pk}/controls",
        {
            "id": str(uuid.uuid4()),
            "mode": "scheduled",
            "scheduled_date": str(today_in_bogota() + timedelta(days=2)),
            "assignee_id": str(owner.pk),
        },
        format="json",
    )

    assert listed(client.get(URL)) == []


def test_a_monitoring_without_presence_adds_nothing(client, plot):
    PhytosanitaryMonitoringFactory(activity=done_monitoring(plot=plot), no_presence=True)

    assert listed(client.get(URL)) == []


def test_it_does_not_make_a_query_per_detection(client, plot):
    detection_on(plot, date(2026, 10, 1))
    with CaptureQueriesContext(connection) as one:
        client.get(URL)

    for day in range(2, 9):
        detection_on(PlotFactory(farm=plot.farm), date(2026, 10, day))
    with CaptureQueriesContext(connection) as many:
        client.get(URL)

    assert len(many) == len(one)


# --- Quién lo ve --------------------------------------------------------------------------------


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farms=[farm]), get_system_role(FOREMAN))


def test_the_foreman_sees_only_the_detections_of_their_farm(auth_client, plot, farm):
    own = detection_on(plot, date(2026, 10, 1))
    detection_on(PlotFactory(farm=FarmFactory(producer=farm.producer)), date(2026, 10, 1))

    assert listed(auth_client(foreman_of(farm)).get(URL)) == [str(own.pk)]


def test_another_producer_does_not_see_them(auth_client, plot):
    detection_on(plot, date(2026, 10, 1))
    stranger = make_producer_owner(ProducerFactory())

    assert listed(auth_client(stranger).get(URL)) == []


def test_who_does_not_schedule_gets_a_403(auth_client, farm):
    worker = make_delegate(farm.producer, [COMPLETE], farm=farm)

    assert auth_client(worker).get(URL).status_code == 403


def test_the_association_gets_a_403(auth_client):
    assert auth_client(make_administrator()).get(URL).status_code == 403


def test_the_technical_account_can_narrow_by_producer(auth_client, plot):
    own = detection_on(plot, date(2026, 10, 1))
    detection_on(PlotFactory(), date(2026, 10, 1))
    client = auth_client(UserFactory(is_superuser=True))

    everything = client.get(URL)
    narrowed = client.get(URL, {"producer": str(plot.farm.producer_id)})

    assert len(listed(everything)) == 2
    assert listed(narrowed) == [str(own.pk)]


def test_without_a_session_it_is_a_401(api_client):
    assert api_client.get(URL).status_code == 401
