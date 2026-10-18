from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityType
from apps.activities.tests.factories import AgriculturalActivityFactory, done_activity
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

URL = "/api/agricultural-activities/pending"
VIEW = ["farms.view_farm", "plots.view_plot", "activities.view_agriculturalactivity"]
THROUGH = {"through": "2026-10-27"}


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def plot(producer):
    return PlotFactory(farm__producer=producer)


@pytest.fixture
def client(auth_client, producer):
    return auth_client(UserFactory(producer=producer, permissions=VIEW))


def on(plot, day, **kwargs):
    return AgriculturalActivityFactory(plot=plot, scheduled_date=day, **kwargs)


def listed(response):
    assert response.status_code == 200, response.json()
    return [row["id"] for row in response.json()["results"]]


def test_an_open_activity_older_than_the_period_limit_is_listed(client, plot):
    old = on(plot, date(2026, 3, 2))

    assert listed(client.get(URL, THROUGH)) == [str(old.pk)]


def test_a_type_keeps_only_the_pending_of_that_type(client, plot):
    monitoring = on(plot, date(2026, 10, 2), activity_type=ActivityType.PHYTOSANITARY_MONITORING)
    on(plot, date(2026, 10, 3), activity_type=ActivityType.PRUNING)

    response = client.get(URL, {**THROUGH, "activity_type": "phytosanitary_monitoring"})

    assert listed(response) == [str(monitoring.pk)]


def test_without_a_type_every_pending_activity_is_listed(client, plot):
    first = on(plot, date(2026, 10, 2), activity_type=ActivityType.PHYTOSANITARY_MONITORING)
    second = on(plot, date(2026, 10, 3), activity_type=ActivityType.PRUNING)

    assert set(listed(client.get(URL, THROUGH))) == {str(first.pk), str(second.pk)}


def test_a_type_that_does_not_exist_is_a_400(client):
    response = client.get(URL, {**THROUGH, "activity_type": "dancing"})

    assert response.status_code == 400
    assert "activity_type" in response.json()["fields"]


def test_done_activities_are_not_listed(client, plot):
    pending = on(plot, date(2026, 10, 2))
    done_activity(plot=plot, scheduled_date=date(2026, 10, 1))

    assert listed(client.get(URL, THROUGH)) == [str(pending.pk)]


def test_the_activities_after_the_limit_are_left_out_and_the_limit_day_is_kept(client, plot):
    on_the_limit = on(plot, date(2026, 10, 27))
    on(plot, date(2026, 10, 28))

    assert listed(client.get(URL, THROUGH)) == [str(on_the_limit.pk)]


def test_it_is_ordered_by_date_and_type(client, plot):
    later = on(plot, date(2026, 10, 9), activity_type=ActivityType.IRRIGATION)
    weeds = on(plot, date(2026, 10, 2), activity_type=ActivityType.WEED_CONTROL)
    fertilization = on(plot, date(2026, 10, 2), activity_type=ActivityType.FERTILIZATION)

    assert listed(client.get(URL, THROUGH)) == [
        str(fertilization.pk),
        str(weeds.pk),
        str(later.pk),
    ]


def test_each_row_carries_its_computed_state(client, plot):
    on(plot, date(2026, 10, 2))

    row = client.get(URL, THROUGH).json()["results"][0]

    assert {"state", "days_late", "plot", "assignee"} <= set(row)


def test_only_the_activities_of_the_producer(client, plot):
    own = on(plot, date(2026, 10, 2))
    on(PlotFactory(), date(2026, 10, 2))

    assert listed(client.get(URL, THROUGH)) == [str(own.pk)]


@pytest.mark.parametrize(
    "params",
    [{}, {"through": "no-es-fecha"}, {"through": "2026-13-40"}],
    ids=["missing", "not-a-date", "impossible-date"],
)
def test_an_invalid_limit_is_400(client, params):
    response = client.get(URL, params)

    assert response.status_code == 400
    assert "through" in response.json()["fields"]


def test_the_producer_filter_of_another_account_is_ignored(client, plot):
    own = on(plot, date(2026, 10, 2))
    foreign = on(PlotFactory(), date(2026, 10, 2))

    response = client.get(URL, {**THROUGH, "producer": str(foreign.plot.farm.producer_id)})

    assert listed(response) == [str(own.pk)]


def test_the_technical_account_sees_every_producer_or_filters_by_one(auth_client, plot):
    own = on(plot, date(2026, 10, 2))
    other = on(PlotFactory(), date(2026, 10, 3))
    client = auth_client(UserFactory(is_superuser=True))

    assert listed(client.get(URL, THROUGH)) == [str(own.pk), str(other.pk)]
    filtered = client.get(URL, {**THROUGH, "producer": str(plot.farm.producer_id)})
    assert listed(filtered) == [str(own.pk)]


def test_without_the_view_permission_it_is_403(auth_client, producer):
    client = auth_client(UserFactory(producer=producer, permissions=VIEW[:2]))

    assert client.get(URL, THROUGH).status_code == 403


def test_without_a_session_it_is_401(api_client):
    assert api_client.get(URL, THROUGH).status_code == 401


def test_the_route_is_not_taken_for_an_activity_id(client):
    # Si `pending` se leyera como un `{id}`, respondería 404 por no ser un UUID.
    assert client.get(URL, THROUGH).status_code == 200


def test_the_number_of_queries_does_not_grow_with_the_activities(client, plot):
    on(plot, date(2026, 10, 2))
    with CaptureQueriesContext(connection) as one:
        client.get(URL, THROUGH)

    for day in range(3, 9):
        on(PlotFactory(farm=plot.farm), date(2026, 10, day))
    with CaptureQueriesContext(connection) as many:
        client.get(URL, THROUGH)

    assert len(many) == len(one)
