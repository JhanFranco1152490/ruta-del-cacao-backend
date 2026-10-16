"""Consultar cosechas: el periodo, los filtros, el alcance por finca y los recolectores."""

from datetime import date
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
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

OCTOBER = {"from": "2026-10-01", "to": "2026-10-31"}


class Estate:
    """Un productor con dos fincas, una parcela con cosecha en cada una y un capataz en la A."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm_a = FarmFactory(producer=self.producer)
        self.farm_b = FarmFactory(producer=self.producer)
        self.plot_a = characterized_plot(farm=self.farm_a, area_hectares=Decimal("5.00"))
        self.plot_b = characterized_plot(farm=self.farm_b, area_hectares=Decimal("5.00"))
        self.harvest_a = HarvestFactory(plot=self.plot_a, harvest_date=date(2026, 10, 14))
        self.harvest_b = HarvestFactory(plot=self.plot_b, harvest_date=date(2026, 10, 15))
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm_a), get_system_role(FOREMAN)
        )


@pytest.fixture
def estate():
    return Estate()


def ids(response):
    return [item["id"] for item in response.data["results"]]


def test_lists_the_period_most_recent_first(auth_client, estate):
    older = HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 10, 2))
    same_day = HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 10, 15))

    response = auth_client(estate.owner).get("/api/harvests", OCTOBER)

    assert response.status_code == 200
    assert ids(response)[-1] == str(older.pk)
    assert set(ids(response)[:2]) == {str(same_day.pk), str(estate.harvest_b.pk)}
    assert "count" not in response.data


def test_the_period_includes_both_ends_and_leaves_the_rest_out(auth_client, estate):
    first = HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 10, 1))
    last = HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 10, 31))
    HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 9, 30))
    HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 11, 1))

    response = auth_client(estate.owner).get("/api/harvests", OCTOBER)

    assert {str(first.pk), str(last.pk)} <= set(ids(response))
    assert len(ids(response)) == 4


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"from": "2026-10-01"},
        {"to": "2026-10-31"},
        {"from": "2026-10-31", "to": "2026-10-01"},
        {"from": "ayer", "to": "2026-10-31"},
        {"from": "2026-01-01", "to": "2026-04-03"},
    ],
    ids=["none", "no_to", "no_from", "inverted", "bad_date", "93_days"],
)
def test_the_period_is_required_and_limited(auth_client, estate, params):
    response = auth_client(estate.owner).get("/api/harvests", params)

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_a_period_of_ninety_two_days_is_accepted(auth_client, estate):
    response = auth_client(estate.owner).get(
        "/api/harvests", {"from": "2026-01-01", "to": "2026-04-02"}
    )

    assert response.status_code == 200


def test_filters_by_farm_and_plot(auth_client, estate):
    client = auth_client(estate.owner)

    by_farm = client.get("/api/harvests", {**OCTOBER, "farm": str(estate.farm_b.pk)})
    by_plot = client.get("/api/harvests", {**OCTOBER, "plot": str(estate.plot_a.pk)})

    assert ids(by_farm) == [str(estate.harvest_b.pk)]
    assert ids(by_plot) == [str(estate.harvest_a.pk)]


def test_a_farm_or_plot_of_another_producer_gives_an_empty_list(auth_client, estate):
    stranger_plot = characterized_plot()
    HarvestFactory(plot=stranger_plot, harvest_date=date(2026, 10, 3))
    client = auth_client(estate.owner)

    by_farm = client.get("/api/harvests", {**OCTOBER, "farm": str(stranger_plot.farm_id)})
    by_plot = client.get("/api/harvests", {**OCTOBER, "plot": str(stranger_plot.pk)})

    assert (by_farm.status_code, ids(by_farm)) == (200, [])
    assert (by_plot.status_code, ids(by_plot)) == (200, [])


def test_the_foreman_only_sees_the_harvests_of_their_farm(auth_client, estate):
    response = auth_client(estate.foreman).get("/api/harvests", OCTOBER)

    assert ids(response) == [str(estate.harvest_a.pk)]


def test_an_employee_without_a_farm_sees_nothing(auth_client, estate):
    nobody = make_delegate(estate.producer, ["harvests.view_harvest"])

    response = auth_client(nobody).get("/api/harvests", OCTOBER)

    assert response.status_code == 200
    assert ids(response) == []


def test_the_producer_sees_every_farm(auth_client, estate):
    response = auth_client(estate.owner).get("/api/harvests", OCTOBER)

    assert set(ids(response)) == {str(estate.harvest_a.pk), str(estate.harvest_b.pk)}


def test_another_producer_sees_none_of_it(auth_client, estate):
    other = make_producer_owner(ProducerFactory())

    assert ids(auth_client(other).get("/api/harvests", OCTOBER)) == []


def test_the_technical_account_sees_everything_and_can_filter_by_producer(auth_client, estate):
    stranger_plot = characterized_plot()
    stranger = HarvestFactory(plot=stranger_plot, harvest_date=date(2026, 10, 3))
    client = auth_client(UserFactory(is_superuser=True))

    everyone = client.get("/api/harvests", OCTOBER)
    one = client.get("/api/harvests", {**OCTOBER, "producer": str(estate.producer.pk)})

    assert str(stranger.pk) in ids(everyone) and len(ids(everyone)) == 3
    assert set(ids(one)) == {str(estate.harvest_a.pk), str(estate.harvest_b.pk)}


def test_the_producer_filter_is_ignored_for_other_accounts(auth_client, estate):
    response = auth_client(estate.foreman).get(
        "/api/harvests", {**OCTOBER, "producer": str(ProducerFactory().pk)}
    )

    assert ids(response) == [str(estate.harvest_a.pk)]


def test_the_association_and_anonymous_users_cannot_list(auth_client, anonymous_client, estate):
    assert auth_client(make_administrator()).get("/api/harvests", OCTOBER).status_code == 403
    assert anonymous_client.get("/api/harvests", OCTOBER).status_code in (401, 403)


def test_without_the_permission_it_is_forbidden(auth_client, estate):
    worker = make_delegate(estate.producer, ["plots.view_plot"], farm=estate.farm_a)

    assert auth_client(worker).get("/api/harvests", OCTOBER).status_code == 403


def test_the_list_query_count_does_not_grow_with_the_harvests(auth_client, estate):
    client = auth_client(estate.owner)
    with CaptureQueriesContext(connection) as few:
        client.get("/api/harvests", OCTOBER)
    for day in range(3, 13):
        HarvestFactory(plot=estate.plot_a, harvest_date=date(2026, 10, day))

    with CaptureQueriesContext(connection) as many:
        response = client.get("/api/harvests", OCTOBER)

    assert len(response.data["results"]) == 12
    assert len(many) == len(few)


def test_the_detail_returns_the_harvest(auth_client, estate):
    response = auth_client(estate.owner).get(f"/api/harvests/{estate.harvest_a.pk}")

    assert response.status_code == 200
    assert response.data["id"] == str(estate.harvest_a.pk)
    assert response.data["plot"]["code"] == "P01"
    assert response.data["lot"] is None


def test_the_detail_of_what_is_out_of_reach_does_not_exist(auth_client, estate):
    foreman = auth_client(estate.foreman)
    stranger = HarvestFactory()

    assert foreman.get(f"/api/harvests/{estate.harvest_b.pk}").status_code == 404
    assert foreman.get(f"/api/harvests/{stranger.pk}").status_code == 404


# --- Recolectores -------------------------------------------------------------------------


def collectors(client, **params):
    response = client.get("/api/harvests/collectors", params)
    return response, {item["id"]: item for item in response.data.get("results", [])}


def test_collectors_list_who_can_be_named_with_their_farms(auth_client, estate):
    worker = make_delegate(estate.producer, ["harvests.add_harvest"], farm=estate.farm_b)
    viewer = make_delegate(estate.producer, ["harvests.view_harvest"], farm=estate.farm_a)

    response, found = collectors(auth_client(estate.owner))

    assert response.status_code == 200
    assert found[str(estate.foreman.pk)]["farm_ids"] == [str(estate.farm_a.pk)]
    assert found[str(estate.foreman.pk)]["assignable"] is True
    assert found[str(worker.pk)]["farm_ids"] == [str(estate.farm_b.pk)]
    assert found[str(viewer.pk)]["assignable"] is False
    assert found[str(estate.owner.pk)] == {
        "id": str(estate.owner.pk),
        "full_name": found[str(estate.owner.pk)]["full_name"],
        "is_active": True,
        "farm_ids": [],
        "all_farms": True,
        "assignable": True,
    }


def test_a_foreman_cannot_name_the_producer_and_only_sees_their_farm_mates(auth_client, estate):
    elsewhere = grant_role(
        UserFactory(producer=estate.producer, farm=estate.farm_b), get_system_role(FOREMAN)
    )

    _, found = collectors(auth_client(estate.foreman))

    assert found[str(estate.owner.pk)]["assignable"] is False
    assert str(elsewhere.pk) not in found


def test_an_inactive_collector_is_listed_but_marked(auth_client, estate):
    estate.foreman.is_active = False
    estate.foreman.save()

    _, found = collectors(auth_client(estate.owner))

    assert found[str(estate.foreman.pk)]["is_active"] is False


def test_the_technical_account_must_say_the_producer(auth_client, estate):
    client = auth_client(UserFactory(is_superuser=True))

    missing, _ = collectors(client)
    named, found = collectors(client, producer=str(estate.producer.pk))

    assert missing.status_code == 400
    assert named.status_code == 200
    assert str(estate.foreman.pk) in found


def test_collectors_need_the_permission_to_view_harvests(auth_client, estate):
    worker = make_delegate(estate.producer, ["plots.view_plot"], farm=estate.farm_a)

    assert auth_client(worker).get("/api/harvests/collectors").status_code == 403
    assert auth_client(make_administrator()).get("/api/harvests/collectors").status_code == 403
