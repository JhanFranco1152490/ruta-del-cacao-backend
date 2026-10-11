from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.activities.tests.factories import AgriculturalActivityInputFactory, done_activity
from apps.inputs.tests.factories import AgriculturalInputFactory
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

URL = "/api/agricultural-activities"
VIEW = ["farms.view_farm", "plots.view_plot", "activities.view_agriculturalactivity"]


@pytest.fixture
def plot():
    return PlotFactory()


@pytest.fixture
def client(auth_client, plot):
    return auth_client(UserFactory(producer=plot.farm.producer, permissions=VIEW))


def used(activity, quantity="2", **input_fields):
    item = AgriculturalInputFactory(producer=activity.plot.farm.producer, **input_fields)
    return AgriculturalActivityInputFactory(
        activity=activity, input=item, quantity=Decimal(quantity)
    )


def test_a_done_activity_shows_its_inputs_with_their_quantity(client, plot):
    activity = done_activity(plot=plot)
    row = used(
        activity,
        "100",
        name="Urea 46 %",
        unit="kg",
        package_type="sack",
        package_size=Decimal("50"),
    )

    data = client.get(f"{URL}/{activity.pk}").json()

    assert data["inputs"] == [
        {
            "input": {
                "id": str(row.input_id),
                "name": "Urea 46 %",
                "unit": "kg",
                "package_type": "sack",
                "package_size": "50.000",
                "is_active": True,
            },
            "quantity": "100.000",
        }
    ]


def test_inputs_are_listed_by_name(client, plot):
    activity = done_activity(plot=plot)
    used(activity, name="Urea 46 %")
    used(activity, name="Cal dolomita")

    names = [row["input"]["name"] for row in client.get(f"{URL}/{activity.pk}").json()["inputs"]]

    assert names == ["Cal dolomita", "Urea 46 %"]


def test_an_input_deactivated_later_is_still_shown(client, plot):
    activity = done_activity(plot=plot)
    row = used(activity)
    row.input.is_active = False
    row.input.save(update_fields=["is_active"])

    [shown] = client.get(f"{URL}/{activity.pk}").json()["inputs"]

    assert shown["input"]["is_active"] is False


def test_the_list_does_not_query_once_per_input(client, plot):
    day = date.today()
    period = {"from": day.isoformat(), "to": day.isoformat()}
    used(done_activity(plot=plot))
    with CaptureQueriesContext(connection) as one:
        client.get(URL, period)

    for _ in range(4):
        activity = done_activity(plot=plot)
        used(activity)
        used(activity)
    with CaptureQueriesContext(connection) as many:
        response = client.get(URL, period)

    assert len(response.json()["results"]) == 5
    assert len(many) == len(one)
