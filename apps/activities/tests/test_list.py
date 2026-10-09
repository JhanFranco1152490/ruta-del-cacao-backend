from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityType
from apps.activities.tests.factories import AgriculturalActivityFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

URL = "/api/agricultural-activities"
VIEW = ["farms.view_farm", "plots.view_plot", "activities.view_agriculturalactivity"]
OCTOBER = {"from": "2026-10-01", "to": "2026-10-31"}


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


def test_it_lists_the_activities_of_the_period_both_ends_included(client, plot):
    first = on(plot, date(2026, 10, 1))
    last = on(plot, date(2026, 10, 31))
    on(plot, date(2026, 9, 30))
    on(plot, date(2026, 11, 1))

    assert listed(client.get(URL, OCTOBER)) == [str(first.pk), str(last.pk)]


def test_it_is_ordered_by_date_and_type(client, plot):
    later = on(plot, date(2026, 10, 9), activity_type=ActivityType.IRRIGATION)
    weeds = on(plot, date(2026, 10, 2), activity_type=ActivityType.WEED_CONTROL)
    fertilization = on(plot, date(2026, 10, 2), activity_type=ActivityType.FERTILIZATION)

    assert listed(client.get(URL, OCTOBER)) == [
        str(fertilization.pk),
        str(weeds.pk),
        str(later.pk),
    ]


def test_each_row_carries_its_computed_state(client, plot):
    on(plot, date(2026, 10, 2))

    row = client.get(URL, OCTOBER).json()["results"][0]

    assert {"state", "days_late", "plot", "assignee"} <= set(row)


def test_only_the_activities_of_the_producer(client, plot):
    own = on(plot, date(2026, 10, 2))
    on(PlotFactory(), date(2026, 10, 2))

    assert listed(client.get(URL, OCTOBER)) == [str(own.pk)]


@pytest.mark.parametrize(
    "params, field",
    [
        ({"to": "2026-10-31"}, "from"),
        ({"from": "2026-10-01"}, "to"),
        ({"from": "2026-10-31", "to": "2026-10-01"}, "to"),
        ({"from": "2026-01-01", "to": "2026-06-30"}, "to"),
    ],
    ids=["no-from", "no-to", "backwards", "too-long"],
)
def test_an_invalid_period_is_400(client, params, field):
    response = client.get(URL, params)

    assert response.status_code == 400
    assert field in response.json()["fields"]


def test_a_period_of_exactly_120_days_is_accepted(client):
    start = date(2026, 10, 1)
    end = start + timedelta(days=119)

    assert client.get(URL, {"from": start, "to": end}).status_code == 200


def test_the_producer_filter_of_another_account_is_ignored(client, plot):
    own = on(plot, date(2026, 10, 2))
    foreign = on(PlotFactory(), date(2026, 10, 2))

    response = client.get(URL, {**OCTOBER, "producer": str(foreign.plot.farm.producer_id)})

    assert listed(response) == [str(own.pk)]


def test_the_technical_account_sees_every_producer_or_filters_by_one(auth_client, plot):
    own = on(plot, date(2026, 10, 2))
    other = on(PlotFactory(), date(2026, 10, 3))
    client = auth_client(UserFactory(is_superuser=True))

    assert listed(client.get(URL, OCTOBER)) == [str(own.pk), str(other.pk)]
    filtered = client.get(URL, {**OCTOBER, "producer": str(plot.farm.producer_id)})
    assert listed(filtered) == [str(own.pk)]


def test_without_the_view_permission_it_is_403(auth_client, producer):
    client = auth_client(UserFactory(producer=producer, permissions=VIEW[:2]))

    assert client.get(URL, OCTOBER).status_code == 403


def test_the_number_of_queries_does_not_grow_with_the_activities(client, plot):
    on(plot, date(2026, 10, 2))
    with CaptureQueriesContext(connection) as one:
        client.get(URL, OCTOBER)

    for day in range(3, 9):
        on(PlotFactory(farm=plot.farm), date(2026, 10, day))
    with CaptureQueriesContext(connection) as many:
        client.get(URL, OCTOBER)

    assert len(many) == len(one)
