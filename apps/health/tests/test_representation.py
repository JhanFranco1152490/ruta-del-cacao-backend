"""El resultado del monitoreo (`monitoring`) y la detección que atiende un control (`control_of`)
en la representación de la actividad, en todos los endpoints de actividades."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.state import today_in_bogota
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.health.choices import ControlMethod, SamplingMethod
from apps.health.tests.factories import (
    DetectionFactory,
    PestDiseaseFactory,
    PhytosanitaryMonitoringFactory,
    PhytosanitaryTreatmentFactory,
    done_monitoring,
)
from apps.inputs.tests.factories import AgriculturalInputFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

URL = "/api/agricultural-activities"


@pytest.fixture
def plot():
    return PlotFactory()


@pytest.fixture
def client(auth_client, plot):
    return auth_client(make_producer_owner(plot.farm.producer))


def detail(client, activity):
    response = client.get(f"{URL}/{activity.pk}")
    assert response.status_code == 200
    return response.json()


def done_control(detection, **kwargs):
    activity = AgriculturalActivityFactory(
        plot=detection.monitoring.activity.plot,
        activity_type=ActivityType.PHYTOSANITARY_CONTROL,
        scheduled_date=detection.monitoring.activity.done_date,
        status=ActivityStatus.DONE,
        done_date=detection.monitoring.activity.done_date,
        completed_at=timezone.now(),
    )
    return PhytosanitaryTreatmentFactory(activity=activity, detection=detection, **kwargs)


@pytest.fixture
def recorded(plot):
    """Un monitoreo de 50 árboles con Monilia en 12, atendida con una remoción de frutos."""
    monitoring = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot),
        sampling_method=SamplingMethod.ZIGZAG,
        notes="Foco de infección en la zona baja.",
    )
    detection = DetectionFactory(
        monitoring=monitoring,
        pest_disease=PestDiseaseFactory(name="Monilia", kind="disease"),
        affected_units=12,
        incidence=Decimal("24.00"),
    )
    treatment = done_control(detection, method=ControlMethod.FRUIT_REMOVAL)
    return monitoring, detection, treatment


def test_a_recorded_monitoring_brings_its_result(client, recorded):
    monitoring, detection, treatment = recorded

    body = detail(client, monitoring.activity)

    assert body["control_of"] is None
    assert body["monitoring"] == {
        "sampling_unit": "trees",
        "evaluated_units": 50,
        "sampling_method": "zigzag",
        "notes": "Foco de infección en la zona baja.",
        "no_presence": False,
        "detections": [
            {
                "id": str(detection.pk),
                "pest_disease": {
                    "id": str(detection.pest_disease_id),
                    "name": "Monilia",
                    "kind": "disease",
                    "is_active": True,
                },
                "other_description": None,
                "affected_units": 12,
                "incidence": "24.00",
                "controls": [
                    {
                        "id": str(treatment.pk),
                        "method": "fruit_removal",
                        "method_description": None,
                        "scheduled_date": str(treatment.activity.scheduled_date),
                        "state": "done",
                        "done_date": str(treatment.activity.done_date),
                    }
                ],
                "control_request": None,
            }
        ],
        "detections_without_control": 0,
        "evidence_count": 0,
    }


def test_a_detection_with_other_has_no_catalog_entry(client, plot):
    monitoring = PhytosanitaryMonitoringFactory(activity=done_monitoring(plot=plot))
    DetectionFactory(
        monitoring=monitoring,
        pest_disease=None,
        other_description="Hormigas en hojas",
        normalized_other="hormigasenhojas",
    )

    row = detail(client, monitoring.activity)["monitoring"]["detections"][0]

    assert (row["pest_disease"], row["other_description"]) == (None, "Hormigas en hojas")


def test_without_presence_there_is_nothing_to_control(client, plot):
    monitoring = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot), no_presence=True
    )

    result = detail(client, monitoring.activity)["monitoring"]

    assert (result["no_presence"], result["detections"]) == (True, [])
    assert result["detections_without_control"] == 0


def test_detections_without_control_are_counted(client, recorded):
    monitoring, _, _ = recorded
    DetectionFactory(monitoring=monitoring)
    DetectionFactory(monitoring=monitoring)

    result = detail(client, monitoring.activity)["monitoring"]

    assert result["detections_without_control"] == 2


def test_a_dismissed_detection_is_not_counted_without_control(client, recorded):
    monitoring, _, _ = recorded
    DetectionFactory(monitoring=monitoring)
    DetectionFactory(monitoring=monitoring, requested=True, control_dismissed_at=timezone.now())

    result = detail(client, monitoring.activity)["monitoring"]

    assert result["detections_without_control"] == 1


def test_a_detection_lists_its_controls_by_date(client, recorded):
    monitoring, detection, first = recorded
    later = PhytosanitaryTreatmentFactory(
        detection=detection,
        activity=AgriculturalActivityFactory(
            plot=monitoring.activity.plot,
            activity_type=ActivityType.PHYTOSANITARY_CONTROL,
            scheduled_date=today_in_bogota() + timedelta(days=4),
        ),
    )

    controls = detail(client, monitoring.activity)["monitoring"]["detections"][0]["controls"]

    assert [row["id"] for row in controls] == [str(first.pk), str(later.pk)]
    assert controls[1]["state"] == "scheduled"
    assert (controls[1]["method"], controls[1]["done_date"]) == (None, None)


def test_a_scheduled_monitoring_has_no_result_yet(client, plot):
    scheduled = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING
    )

    body = detail(client, scheduled)

    assert (body["monitoring"], body["control_of"]) == (None, None)


def test_other_activities_bring_neither(client, plot):
    body = detail(client, AgriculturalActivityFactory(plot=plot))

    assert (body["monitoring"], body["control_of"]) == (None, None)


def test_a_control_says_which_detection_it_attends(client, recorded):
    monitoring, detection, _ = recorded
    item = AgriculturalInputFactory(producer=monitoring.activity.plot.farm.producer)
    control = PhytosanitaryTreatmentFactory(
        detection=detection,
        method=ControlMethod.PRODUCT_APPLICATION,
        planned_input=item,
        activity=AgriculturalActivityFactory(
            plot=monitoring.activity.plot, activity_type=ActivityType.PHYTOSANITARY_CONTROL
        ),
    )

    body = detail(client, control.activity)

    assert body["monitoring"] is None
    assert body["control_of"] == {
        "detection_id": str(detection.pk),
        "monitoring_id": str(monitoring.pk),
        "pest_disease": {
            "id": str(detection.pest_disease_id),
            "name": "Monilia",
            "kind": "disease",
            "is_active": True,
        },
        "other_description": None,
        "incidence": "24.00",
        "sampling_unit": "trees",
        "monitoring_done_date": str(monitoring.activity.done_date),
        "method": "product_application",
        "method_description": None,
        "planned_input": {"id": str(item.pk), "name": item.name, "is_active": True},
        "evidence_count": 0,
    }


def test_the_calendar_list_brings_them_without_a_query_per_activity(client, plot):
    def recorded_on(day):
        monitoring = PhytosanitaryMonitoringFactory(
            activity=done_monitoring(plot=PlotFactory(farm=plot.farm), scheduled_date=day)
        )
        done_control(DetectionFactory(monitoring=monitoring))

    today = today_in_bogota()
    period = {"from": str(today - timedelta(days=10)), "to": str(today)}
    recorded_on(today - timedelta(days=1))
    with CaptureQueriesContext(connection) as one:
        client.get(URL, period)

    for days_ago in range(2, 8):
        recorded_on(today - timedelta(days=days_ago))
    with CaptureQueriesContext(connection) as many:
        response = client.get(URL, period)

    assert len(response.json()["results"]) == 14
    assert len(many) == len(one)


def test_pending_and_the_monitoring_response_bring_them_too(client, plot):
    scheduled = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING
    )

    pending = client.get(f"{URL}/pending", {"through": str(today_in_bogota())}).json()

    assert pending["results"][0]["monitoring"] is None
    assert "control_of" in pending["results"][0]
    assert scheduled.status == ActivityStatus.SCHEDULED
