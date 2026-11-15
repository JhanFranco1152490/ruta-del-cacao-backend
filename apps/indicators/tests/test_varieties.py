from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.producers.tests.factories import ProducerFactory

from .helpers import PERIOD, at, classify, discard_whole, dry, harvest

pytestmark = pytest.mark.django_db

PRODUCER_URL = "/api/indicators/producer"
ASSOCIATION_URL = "/api/indicators/association"


class Orchard:
    """Dos productores. Laura siembra Clon Alfa y TCS; Marcos solo Clon Alfa."""

    def __init__(self):
        self.ccn = CacaoVarietyFactory(name="Clon Alfa")
        self.tcs = CacaoVarietyFactory(name="Clon Beta")
        self.laura = ProducerFactory(first_name="Laura")
        self.marcos = ProducerFactory(first_name="Marcos")
        farm = FarmFactory(producer=self.laura)
        self.ccn_plot = characterized_plot(farm=farm, variety=self.ccn)
        self.tcs_plot = characterized_plot(farm=farm, variety=self.tcs)
        self.marcos_plot = characterized_plot(
            farm=FarmFactory(producer=self.marcos), variety=self.ccn
        )
        dry(harvest(self.ccn_plot, date(2026, 1, 10), "400.0"), "136.0")
        harvest(self.tcs_plot, date(2026, 2, 5), "200.0")
        harvest(self.marcos_plot, date(2026, 3, 1), "100.0")
        classify(self.ccn_plot, "90.0", "10.0", "0.0", at(2026, 2, 20, 9))
        discard_whole(self.tcs_plot, "30.0", at(2026, 3, 5, 9))
        self.administrator = make_administrator()
        self.owner = make_producer_owner(self.laura)


@pytest.fixture
def orchard():
    return Orchard()


def varieties(client, url, **params):
    response = client.get(url, {**PERIOD, **params})
    assert response.status_code == 200, response.content
    return {row["variety_name"]: row for row in response.json()["varieties"]}


def test_the_producer_panel_splits_production_and_quality_by_variety(auth_client, orchard):
    rows = varieties(auth_client(orchard.owner), PRODUCER_URL)

    assert set(rows) == {"Clon Alfa", "Clon Beta"}
    assert (rows["Clon Alfa"]["green_kg"], rows["Clon Alfa"]["dry_kg"]) == ("400.0", "136.0")
    assert (rows["Clon Alfa"]["g1_kg"], rows["Clon Alfa"]["g1_pct"]) == ("90.0", "90.0")
    assert (rows["Clon Beta"]["green_kg"], rows["Clon Beta"]["dry_kg"]) == ("200.0", "0.0")
    assert (rows["Clon Beta"]["discard_kg"], rows["Clon Beta"]["discard_pct"]) == ("30.0", "100.0")


def test_the_varieties_come_from_the_biggest_to_the_smallest(auth_client, orchard):
    response = auth_client(orchard.administrator).get(ASSOCIATION_URL, PERIOD)

    names = [row["variety_name"] for row in response.json()["varieties"]]
    assert names == ["Clon Alfa", "Clon Beta"]


def test_the_association_adds_a_variety_over_all_producers(auth_client, orchard):
    rows = varieties(auth_client(orchard.administrator), ASSOCIATION_URL)

    assert rows["Clon Alfa"]["green_kg"] == "500.0"


def test_the_producer_panel_only_counts_the_own_varieties(auth_client, orchard):
    producer_rows = varieties(auth_client(orchard.owner), PRODUCER_URL)

    assert producer_rows["Clon Alfa"]["green_kg"] == "400.0"


def test_a_variety_without_figures_in_the_period_does_not_appear(auth_client, orchard):
    CacaoVarietyFactory(name="Sin cifras")

    assert "Sin cifras" not in varieties(auth_client(orchard.administrator), ASSOCIATION_URL)


def test_the_association_panel_can_be_narrowed_to_one_producer(auth_client, orchard):
    client = auth_client(orchard.administrator)

    data = client.get(ASSOCIATION_URL, {**PERIOD, "producer": str(orchard.marcos.pk)}).json()

    assert data["totals"]["producers"] == 1
    assert data["totals"]["green_kg"] == "100.0"
    assert [farm["producer"]["id"] for farm in data["farms"]] == [str(orchard.marcos.pk)]
    assert [row["variety_name"] for row in data["varieties"]] == ["Clon Alfa"]
    assert data["varieties"][0]["green_kg"] == "100.0"


def test_a_producer_without_farms_leaves_the_panel_empty(auth_client, orchard):
    data = (
        auth_client(orchard.administrator)
        .get(ASSOCIATION_URL, {**PERIOD, "producer": str(ProducerFactory().pk)})
        .json()
    )

    assert data["farms"] == []
    assert data["varieties"] == []
    assert data["totals"]["farms"] == 0


def test_a_malformed_producer_is_a_validation_error(auth_client, orchard):
    response = auth_client(orchard.administrator).get(ASSOCIATION_URL, {**PERIOD, "producer": "x"})

    assert response.status_code == 400


def test_the_varieties_do_not_query_once_per_variety(auth_client, orchard):
    client = auth_client(orchard.administrator)
    with CaptureQueriesContext(connection) as small:
        client.get(ASSOCIATION_URL, PERIOD)
    for _ in range(3):
        plot = characterized_plot(farm=FarmFactory(), variety=CacaoVarietyFactory())
        harvest(plot, date(2026, 2, 1), "10.0")
        classify(plot, "1.0", "0.0", "0.0", at(2026, 2, 2, 9))

    with CaptureQueriesContext(connection) as large:
        client.get(ASSOCIATION_URL, PERIOD)

    assert len(large) == len(small)
