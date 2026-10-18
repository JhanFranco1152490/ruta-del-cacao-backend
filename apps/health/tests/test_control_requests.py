"""Quien registra un monitoreo y no puede programar controles pide que lo programen; el
Productor, el Capataz o quien tenga el permiso lo ve en el aviso y lo programa, o decide que no
requiere control."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate, make_producer_owner
from apps.activities.choices import ActivityType
from apps.activities.models import AgriculturalActivity
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.tests.factories import FarmFactory
from apps.health.models import Detection
from apps.health.tests.factories import PestDiseaseFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

COMPLETE = "activities.complete_agriculturalactivity"
WAITING = "/api/phytosanitary-detections/without-control"


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farms=[farm]), get_system_role(FOREMAN))


@pytest.fixture
def plot():
    return PlotFactory()


@pytest.fixture
def worker(plot):
    """Un operario que registra lo suyo y no programa controles."""
    worker = make_delegate(
        plot.farm.producer, [COMPLETE, "activities.view_agriculturalactivity"], farm=plot.farm
    )
    worker.first_name, worker.last_name = "Luis", "Mora"
    worker.save(update_fields=["first_name", "last_name"])
    return worker


@pytest.fixture
def foreman(plot):
    return foreman_of(plot.farm)


@pytest.fixture
def monitoring(plot, worker):
    activity = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING, assignee=worker
    )
    AgriculturalActivity.objects.filter(pk=activity.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )
    return activity


@pytest.fixture
def monilia():
    return PestDiseaseFactory(name="Monilia")


def result(pest, detection_id, **detection):
    return {
        "done_date": str(today_in_bogota()),
        "sampling_unit": "trees",
        "evaluated_units": 50,
        "detections": [
            {
                "id": str(detection_id),
                "pest_disease_id": str(pest.pk),
                "affected_units": 12,
                **detection,
            }
        ],
    }


def record(client, monitoring, body):
    return client.post(
        f"/api/agricultural-activities/{monitoring.pk}/monitoring", body, format="json"
    )


def waiting_ids(client) -> list[str]:
    response = client.get(WAITING)
    assert response.status_code == 200
    return [row["id"] for row in response.json()["results"]]


def no_control_needed(client, detection_id):
    return client.post(f"/api/phytosanitary-detections/{detection_id}/no-control-needed")


# --- Pedir que lo programen ---------------------------------------------------------------------


def test_a_worker_asks_for_a_control_and_the_foreman_sees_who_asked(
    auth_client, monitoring, monilia, worker, foreman
):
    detection_id = uuid.uuid4()

    response = record(
        auth_client(worker), monitoring, result(monilia, detection_id, control_requested=True)
    )

    assert response.status_code == 201
    detection = Detection.objects.get(pk=detection_id)
    assert detection.control_requested_by == worker
    assert detection.control_requested_at is not None
    rows = auth_client(foreman).get(WAITING).json()["results"]
    assert [row["id"] for row in rows] == [str(detection_id)]
    assert rows[0]["control_requested_by"] == {"id": str(worker.pk), "full_name": "Luis Mora"}
    assert rows[0]["control_requested_at"] is not None


def test_none_for_now_does_not_warn_anyone(auth_client, monitoring, monilia, worker, foreman):
    response = record(auth_client(worker), monitoring, result(monilia, uuid.uuid4()))

    assert response.status_code == 201
    assert waiting_ids(auth_client(foreman)) == []


def test_asking_and_sending_a_control_at_once_is_a_400(auth_client, monitoring, monilia, worker):
    body = result(
        monilia,
        uuid.uuid4(),
        control_requested=True,
        control={"id": str(uuid.uuid4()), "mode": "done", "method": "fruit_removal"},
    )

    response = record(auth_client(worker), monitoring, body)

    assert response.status_code == 400
    assert "detections" in response.json()["fields"]
    assert not Detection.objects.exists()


def test_the_request_is_shown_in_the_monitoring(auth_client, monitoring, monilia, worker):
    detection_id = uuid.uuid4()
    record(auth_client(worker), monitoring, result(monilia, detection_id, control_requested=True))

    detail = auth_client(worker).get(f"/api/agricultural-activities/{monitoring.pk}").json()

    request = detail["monitoring"]["detections"][0]["control_request"]
    assert request["requested_by"] == {"id": str(worker.pk), "full_name": "Luis Mora"}
    assert (request["dismissed_by"], request["dismissed_at"]) == (None, None)


def test_a_detection_nobody_asked_about_has_no_request(auth_client, monitoring, monilia, worker):
    record(auth_client(worker), monitoring, result(monilia, uuid.uuid4()))

    detail = auth_client(worker).get(f"/api/agricultural-activities/{monitoring.pk}").json()

    assert detail["monitoring"]["detections"][0]["control_request"] is None


def test_resending_the_same_request_is_a_200_and_without_it_a_409(
    auth_client, monitoring, monilia, worker
):
    detection_id = uuid.uuid4()
    body = result(monilia, detection_id, control_requested=True)
    client = auth_client(worker)
    record(client, monitoring, body)

    again = record(client, monitoring, body)
    without = record(client, monitoring, result(monilia, detection_id))

    assert again.status_code == 200
    assert without.status_code == 409


# --- Atender la solicitud -----------------------------------------------------------------------


@pytest.fixture
def requested(auth_client, monitoring, monilia, worker):
    detection_id = uuid.uuid4()
    record(auth_client(worker), monitoring, result(monilia, detection_id, control_requested=True))
    return detection_id


def test_programming_the_control_answers_the_request(auth_client, requested, foreman):
    client = auth_client(foreman)

    client.post(
        f"/api/phytosanitary-detections/{requested}/controls",
        {
            "id": str(uuid.uuid4()),
            "mode": "scheduled",
            "scheduled_date": str(today_in_bogota() + timedelta(days=2)),
            "assignee_id": str(foreman.pk),
        },
        format="json",
    )

    assert waiting_ids(client) == []


def test_the_foreman_decides_no_control_is_needed(auth_client, requested, foreman):
    client = auth_client(foreman)

    response = no_control_needed(client, requested)

    assert response.status_code == 204
    assert waiting_ids(client) == []
    detection = Detection.objects.get(pk=requested)
    assert detection.control_dismissed_by == foreman
    assert detection.control_dismissed_at is not None


def test_deciding_it_again_keeps_who_decided_first(auth_client, requested, foreman, plot):
    no_control_needed(auth_client(foreman), requested)
    owner = make_producer_owner(plot.farm.producer)

    response = no_control_needed(auth_client(owner), requested)

    assert response.status_code == 204
    assert Detection.objects.get(pk=requested).control_dismissed_by == foreman


def test_the_decision_is_shown_in_the_monitoring(auth_client, requested, foreman, monitoring):
    no_control_needed(auth_client(foreman), requested)

    detail = auth_client(foreman).get(f"/api/agricultural-activities/{monitoring.pk}").json()

    request = detail["monitoring"]["detections"][0]["control_request"]
    assert request["dismissed_by"]["id"] == str(foreman.pk)
    assert request["dismissed_at"] is not None


def test_who_does_not_schedule_cannot_decide_it(auth_client, requested, worker):
    response = no_control_needed(auth_client(worker), requested)

    assert response.status_code == 403
    assert Detection.objects.get(pk=requested).control_dismissed_at is None


def test_another_farm_cannot_decide_it(auth_client, requested, plot):
    elsewhere = foreman_of(FarmFactory(producer=plot.farm.producer))

    assert no_control_needed(auth_client(elsewhere), requested).status_code == 404


def test_a_detection_that_does_not_exist_is_a_404(auth_client, foreman):
    assert no_control_needed(auth_client(foreman), uuid.uuid4()).status_code == 404
