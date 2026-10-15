"""Un monitoreo realizado es un registro del negocio: su parcela, su finca y su productor no se
eliminan, se desactivan. Un control programado se elimina como cualquier actividad, y su detección
vuelve a esperar un control. Se prueba por las APIs de las otras apps, que no saben nada de
sanidad."""

import pytest

from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.health.models import Detection, PhytosanitaryMonitoring, PhytosanitaryTreatment
from apps.health.tests.factories import (
    DetectionFactory,
    PhytosanitaryMonitoringFactory,
    PhytosanitaryTreatmentFactory,
    done_monitoring,
)
from apps.plots.models import Plot
from apps.plots.tests.factories import PlotFactory
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def plot(producer):
    return PlotFactory(farm=FarmFactory(producer=producer))


@pytest.fixture
def owner_client(auth_client, producer):
    return auth_client(make_producer_owner(producer))


@pytest.fixture
def treatment(plot):
    """Un monitoreo realizado con una detección y su control programado."""
    monitoring = PhytosanitaryMonitoringFactory(activity=done_monitoring(plot=plot))
    return PhytosanitaryTreatmentFactory(detection=DetectionFactory(monitoring=monitoring))


def test_a_plot_with_a_recorded_monitoring_is_not_deleted(owner_client, plot, treatment):
    response = owner_client.delete(f"/api/plots/{plot.pk}?expected_version=1")

    assert response.status_code == 409
    assert response.data["code"] == "plot_has_records"
    assert Plot.objects.filter(pk=plot.pk).exists()
    assert PhytosanitaryMonitoring.objects.exists()
    assert PhytosanitaryTreatment.objects.exists()


def test_a_producer_with_a_recorded_monitoring_is_not_deleted(auth_client, producer, treatment):
    response = auth_client(make_administrator()).delete(
        f"/api/producers/{producer.pk}?expected_version=1"
    )

    assert response.status_code == 409
    assert response.data["code"] == "producer_has_records"
    assert Producer.objects.filter(pk=producer.pk).exists()


def test_deleting_a_scheduled_control_leaves_the_detection_waiting(owner_client, treatment):
    control = treatment.activity
    detection_id = treatment.detection_id

    response = owner_client.delete(
        f"/api/agricultural-activities/{control.pk}?expected_version={control.version}"
    )

    assert response.status_code == 204
    assert not PhytosanitaryTreatment.objects.exists()
    assert Detection.objects.filter(pk=detection_id).exists()
    waiting = owner_client.get("/api/phytosanitary-detections/without-control").json()
    assert [row["id"] for row in waiting["results"]] == [str(detection_id)]
