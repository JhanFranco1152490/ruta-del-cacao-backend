from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_administrator, make_producer_owner
from apps.activities.choices import ActivityType
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.farms.tests.factories import FarmFactory
from apps.health.choices import SamplingUnit
from apps.health.tests.factories import (
    DetectionFactory,
    PestDiseaseFactory,
    PhytosanitaryMonitoringFactory,
    done_monitoring,
)
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]


def url(plot) -> str:
    return f"/api/plots/{plot.pk}/phytosanitary-history"


@pytest.fixture
def plot():
    return PlotFactory()


@pytest.fixture
def client(auth_client, plot):
    return auth_client(make_producer_owner(plot.farm.producer))


@pytest.fixture
def monilia():
    return PestDiseaseFactory(name="Monilia", kind="disease")


@pytest.fixture
def trips():
    return PestDiseaseFactory(name="Trips")


def recorded(plot, on, *detections, unit=SamplingUnit.TREES, no_presence=False):
    """Un monitoreo realizado el día `on`, con detecciones `(plaga, incidencia)`; la plaga puede
    ser un texto de Otra."""
    monitoring = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot, scheduled_date=on, done_date=on),
        sampling_unit=unit,
        no_presence=no_presence,
    )
    for pest, incidence in detections:
        if isinstance(pest, str):
            DetectionFactory(
                monitoring=monitoring,
                pest_disease=None,
                other_description=pest,
                normalized_other=pest.lower().replace(" ", ""),
                incidence=Decimal(incidence),
            )
        else:
            DetectionFactory(
                monitoring=monitoring, pest_disease=pest, incidence=Decimal(incidence)
            )
    return monitoring


def ids(response) -> list[str]:
    return [row["id"] for row in response.json()["results"]]


def test_the_history_lists_recorded_monitorings_from_newest_to_oldest(client, plot, monilia):
    old = recorded(plot, date(2026, 9, 1), (monilia, "31.00"))
    new = recorded(plot, date(2026, 10, 1), (monilia, "24.00"))
    AgriculturalActivityFactory(plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING)
    recorded(PlotFactory(farm=plot.farm), date(2026, 10, 5), (monilia, "50.00"))

    response = client.get(url(plot))

    assert response.status_code == 200
    assert ids(response) == [str(new.pk), str(old.pk)]
    first = response.json()["results"][0]
    assert first["monitoring"]["detections"][0]["incidence"] == "24.00"


def test_without_recorded_monitorings_the_history_is_empty(client, plot):
    AgriculturalActivityFactory(plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING)

    response = client.get(url(plot))

    assert response.json() == {"results": [], "summary": []}


def test_the_period_filters_by_the_monitoring_date(client, plot, monilia):
    recorded(plot, date(2026, 8, 31), (monilia, "10.00"))
    inside = recorded(plot, date(2026, 9, 15), (monilia, "20.00"))
    recorded(plot, date(2026, 10, 1), (monilia, "30.00"))

    response = client.get(url(plot), {"from": "2026-09-01", "to": "2026-09-30"})

    assert ids(response) == [str(inside.pk)]


def test_an_inverted_period_is_a_400(client, plot):
    response = client.get(url(plot), {"from": "2026-10-01", "to": "2026-09-01"})

    assert response.status_code == 400
    assert "to" in response.json()["fields"]


def test_a_pest_filter_keeps_only_its_monitorings_and_its_detection(client, plot, monilia, trips):
    both = recorded(plot, date(2026, 10, 1), (monilia, "24.00"), (trips, "6.00"))
    recorded(plot, date(2026, 9, 1), (trips, "4.00"))

    response = client.get(url(plot), {"pest_disease": str(monilia.pk)})

    assert ids(response) == [str(both.pk)]
    detections = response.json()["results"][0]["monitoring"]["detections"]
    assert [row["pest_disease"]["name"] for row in detections] == ["Monilia"]


def test_the_other_filter_keeps_the_detections_of_other(client, plot, monilia):
    with_other = recorded(plot, date(2026, 10, 1), (monilia, "24.00"), ("Hormigas", "6.00"))
    recorded(plot, date(2026, 9, 1), (monilia, "10.00"))

    response = client.get(url(plot), {"other": "true"})

    assert ids(response) == [str(with_other.pk)]
    detections = response.json()["results"][0]["monitoring"]["detections"]
    assert [row["other_description"] for row in detections] == ["Hormigas"]


def test_pest_and_other_together_are_a_400(client, plot, monilia):
    response = client.get(url(plot), {"pest_disease": str(monilia.pk), "other": "true"})

    assert response.status_code == 400


def test_a_monitoring_without_presence_stays_without_a_pest_filter(client, plot, monilia):
    clean = recorded(plot, date(2026, 10, 1), no_presence=True)

    unfiltered = client.get(url(plot))
    filtered = client.get(url(plot), {"pest_disease": str(monilia.pk)})

    assert ids(unfiltered) == [str(clean.pk)]
    assert ids(filtered) == []


# --- Resumen por plaga --------------------------------------------------------------------------


def summary(response) -> dict:
    return {
        (row["pest_disease"]["name"] if row["pest_disease"] else row["other_description"]): row
        for row in response.json()["summary"]
    }


def test_the_summary_gives_the_latest_and_the_previous_incidence(client, plot, monilia, trips):
    recorded(plot, date(2026, 8, 1), (monilia, "40.00"))
    recorded(plot, date(2026, 9, 1), (monilia, "31.00"), (trips, "5.00"))
    recorded(plot, date(2026, 10, 1), (monilia, "24.00"))

    rows = summary(client.get(url(plot)))

    assert rows["Monilia"]["latest_incidence"] == "24.00"
    assert rows["Monilia"]["previous_incidence"] == "31.00"
    assert rows["Monilia"]["latest_date"] == "2026-10-01"
    assert rows["Monilia"]["sampling_unit"] == "trees"
    assert (rows["Trips"]["latest_incidence"], rows["Trips"]["previous_incidence"]) == (
        "5.00",
        None,
    )


def test_the_summary_does_not_compare_pods_with_trees(client, plot, monilia):
    recorded(plot, date(2026, 8, 1), (monilia, "40.00"))
    recorded(plot, date(2026, 9, 1), (monilia, "60.00"), unit=SamplingUnit.PODS)
    recorded(plot, date(2026, 10, 1), (monilia, "24.00"))

    row = summary(client.get(url(plot)))["Monilia"]

    # El anterior que contó árboles, no el de mazorcas que quedó en medio.
    assert (row["latest_incidence"], row["previous_incidence"]) == ("24.00", "40.00")


def test_each_other_text_has_its_own_summary_row(client, plot):
    recorded(plot, date(2026, 9, 1), ("Hormigas", "4.00"), ("Caracoles", "2.00"))
    recorded(plot, date(2026, 10, 1), ("Hormigas", "6.00"))

    rows = summary(client.get(url(plot)))

    assert rows["Hormigas"]["pest_disease"] is None
    assert (rows["Hormigas"]["latest_incidence"], rows["Hormigas"]["previous_incidence"]) == (
        "6.00",
        "4.00",
    )
    assert rows["Caracoles"]["latest_incidence"] == "2.00"


def test_the_summary_follows_the_filters(client, plot, monilia, trips):
    recorded(plot, date(2026, 8, 1), (monilia, "40.00"))
    recorded(plot, date(2026, 10, 1), (monilia, "24.00"), (trips, "5.00"))

    rows = summary(client.get(url(plot), {"from": "2026-09-01"}))

    assert (rows["Monilia"]["latest_incidence"], rows["Monilia"]["previous_incidence"]) == (
        "24.00",
        None,
    )


def test_the_history_does_not_make_a_query_per_monitoring(client, plot, monilia):
    recorded(plot, date(2026, 9, 1), (monilia, "10.00"))
    with CaptureQueriesContext(connection) as one:
        client.get(url(plot))

    for day in range(2, 9):
        recorded(plot, date(2026, 9, day), (monilia, "10.00"), (f"Otra {day}", "1.00"))
    with CaptureQueriesContext(connection) as many:
        client.get(url(plot))

    assert len(many) == len(one)


# --- Quién lo ve --------------------------------------------------------------------------------


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farms=[farm]), get_system_role(FOREMAN))


def test_the_foreman_of_the_farm_reads_it(auth_client, plot, monilia):
    recorded(plot, date(2026, 10, 1), (monilia, "24.00"))

    response = auth_client(foreman_of(plot.farm)).get(url(plot))

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1


def test_the_foreman_of_another_farm_gets_a_404(auth_client, plot):
    other = foreman_of(FarmFactory(producer=plot.farm.producer))

    assert auth_client(other).get(url(plot)).status_code == 404


def test_another_producer_gets_a_404(auth_client, plot):
    stranger = make_producer_owner(ProducerFactory())

    assert auth_client(stranger).get(url(plot)).status_code == 404


def test_a_plot_that_does_not_exist_is_a_404(client):
    missing = PlotFactory.build()

    assert client.get(url(missing)).status_code == 404


def test_the_association_does_not_read_histories(auth_client, plot):
    assert auth_client(make_administrator()).get(url(plot)).status_code == 403


def test_without_a_session_it_is_a_401(api_client, plot):
    assert api_client.get(url(plot)).status_code == 401


def test_a_period_without_end_reaches_today(client, plot, monilia):
    today_one = recorded(plot, date.today() - timedelta(days=1), (monilia, "5.00"))

    response = client.get(url(plot), {"from": str(date.today() - timedelta(days=3))})

    assert ids(response) == [str(today_one.pk)]
