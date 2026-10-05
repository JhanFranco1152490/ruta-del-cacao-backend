from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.crops.services import save_characterization
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

URL = "/api/plot-characterizations"


def history_url(plot) -> str:
    return f"{URL}/{plot.pk}/history"


def content(variety, trees=900, stage="full_production", month=date(2021, 3, 1)):
    return {
        "plantings": [
            {
                "variety_id": variety.pk,
                "planting_date": month,
                "tree_count": trees,
                "propagation": "grafted",
                "stage": stage,
            }
        ],
        "management_system": None,
        "shade_type": None,
        "captured_at": None,
    }


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    user = make_producer_owner(producer)
    user.first_name, user.last_name = "Ana", "Gómez"
    user.save()
    return user


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def plot(producer):
    return PlotFactory(farm__producer=producer)


@pytest.fixture
def ccn51():
    return CacaoVarietyFactory(name="CCN-51")


@pytest.fixture
def edited_three_times(owner, plot, ccn51):
    save_characterization(owner, plot.pk, None, content(ccn51, 900, "establishment"))
    save_characterization(owner, plot.pk, 1, content(ccn51, 900, "full_production"))
    save_characterization(owner, plot.pk, 2, content(ccn51, 1200, "renovation"))


# --- Lectura ------------------------------------------------------------------------------------


def test_the_history_lists_every_version_from_newest_to_oldest(client, plot, edited_three_times):
    response = client.get(history_url(plot))

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert [event["version"] for event in response.data["results"]] == [3, 2, 1]
    assert [event["action"] for event in response.data["results"]] == [
        "updated",
        "updated",
        "created",
    ]


def test_each_event_brings_the_values_of_that_version(client, plot, ccn51, edited_three_times):
    results = client.get(history_url(plot)).data["results"]

    stages = [event["snapshot"]["plantings"][0]["stage"] for event in results]
    assert stages == ["renovation", "full_production", "establishment"]
    assert results[0]["snapshot"]["plantings"][0] == {
        "variety_id": str(ccn51.pk),
        "name": "CCN-51",
        "planting_date": "2021-03",
        "tree_count": 1200,
        "propagation": "grafted",
        "stage": "renovation",
    }
    assert results[0]["changed_fields"] == ["plantings"]
    assert results[0]["occurred_at"]


def test_the_event_names_who_saved_it(client, plot, edited_three_times):
    results = client.get(history_url(plot)).data["results"]

    assert {event["actor_name"] for event in results} == {"Ana Gómez"}


def test_a_deleted_account_leaves_the_version_without_a_name(client, producer, plot, ccn51, owner):
    employee = make_delegate(producer, ["crops.change_plotcharacterization", "plots.view_plot"])
    save_characterization(employee, plot.pk, None, content(ccn51))
    employee.delete()

    results = client.get(history_url(plot)).data["results"]

    assert results[0]["actor_name"] is None


def test_the_history_is_paginated(client, plot, edited_three_times):
    first = client.get(history_url(plot), {"page_size": 2})
    second = client.get(history_url(plot), {"page_size": 2, "page": 2})

    assert set(first.data) == {"count", "next", "previous", "results"}
    assert [event["version"] for event in first.data["results"]] == [3, 2]
    assert first.data["next"] is not None
    assert [event["version"] for event in second.data["results"]] == [1]


def test_a_plot_without_characterization_has_an_empty_history(client, plot):
    response = client.get(history_url(plot))

    assert response.status_code == 200
    assert response.data["results"] == []


def test_the_history_of_an_inactive_plot_can_still_be_read(client, plot, edited_three_times):
    plot.is_active = False
    plot.save()

    assert client.get(history_url(plot)).data["count"] == 3


def test_the_history_takes_the_same_queries_with_few_or_many_versions(client, owner, plot, ccn51):
    save_characterization(owner, plot.pk, None, content(ccn51, 100))
    with CaptureQueriesContext(connection) as few:
        client.get(history_url(plot))

    for version, trees in enumerate(range(200, 700, 100), start=1):
        save_characterization(owner, plot.pk, version, content(ccn51, trees))
    with CaptureQueriesContext(connection) as many:
        response = client.get(history_url(plot))

    assert response.data["count"] == 6
    assert len(many) == len(few)


# --- Permisos y alcance -------------------------------------------------------------------------


def test_the_history_requires_a_session(api_client, plot):
    assert api_client.get(history_url(plot)).status_code == 401


def test_an_employee_who_can_see_plots_reads_the_history(
    auth_client, producer, plot, edited_three_times
):
    employee = make_delegate(producer, ["plots.view_plot"])

    response = auth_client(employee).get(history_url(plot))

    assert response.status_code == 200
    assert response.data["count"] == 3


def test_without_seeing_plots_the_history_is_forbidden(auth_client, producer, plot):
    response = auth_client(UserFactory(producer=producer)).get(history_url(plot))

    assert response.status_code == 403


def test_the_association_does_not_read_the_history(auth_client, plot, edited_three_times):
    response = auth_client(make_administrator()).get(history_url(plot))

    assert response.status_code == 403


def test_the_history_of_another_producers_plot_is_not_found(auth_client, plot, edited_three_times):
    stranger = make_producer_owner(ProducerFactory())

    response = auth_client(stranger).get(history_url(plot))

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


def test_the_history_of_an_unknown_plot_is_not_found(client):
    response = client.get(f"{URL}/00000000-0000-4000-8000-000000000000/history")

    assert response.status_code == 404
