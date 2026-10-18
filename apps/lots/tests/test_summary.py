"""El recuento de lotes por estado: los filtros de la lista menos el estado, y el mismo alcance."""

from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.harvests.tests.factories import HarvestFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.lots.tests.test_read import Estate
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    estate = Estate()
    estate.lot_b.status = LotStatus.FERMENTING
    estate.lot_b.save()
    return estate


def totals(response):
    return {
        row["status"]: (row["count"], row["green_weight_kg"]) for row in response.data["results"]
    }


def test_counts_the_lots_and_kilos_of_every_status_in_order(auth_client, estate):
    harvest = HarvestFactory(
        plot=estate.plot_a, harvest_date=date(2026, 10, 15), green_weight_kg=Decimal("80.0")
    )
    LotFactory(harvest=harvest, code="000123-F01-P01-261015-1")

    response = auth_client(estate.owner).get("/api/lots/summary")

    assert response.status_code == 200
    assert [row["status"] for row in response.data["results"]] == [
        "generated",
        "fermenting",
        "fermented",
        "drying",
        "dried",
    ]
    assert totals(response) == {
        "generated": (2, "200.5"),
        "fermenting": (1, "120.5"),
        "fermented": (0, "0.0"),
        "drying": (0, "0.0"),
        "dried": (0, "0.0"),
    }


def test_the_status_does_not_filter_the_summary(auth_client, estate):
    response = auth_client(estate.owner).get("/api/lots/summary", {"status": "fermenting"})

    assert totals(response)["generated"] == (1, "120.5")
    assert totals(response)["fermenting"] == (1, "120.5")


def test_follows_the_other_filters_of_the_list(auth_client, estate):
    client = auth_client(estate.owner)

    by_farm = client.get("/api/lots/summary", {"farm": str(estate.farm_b.pk)})
    by_search = client.get("/api/lots/summary", {"search": "261014"})
    by_period = client.get("/api/lots/summary", {"from": "2026-10-15"})

    assert totals(by_farm)["generated"][0] == 0 and totals(by_farm)["fermenting"][0] == 1
    assert totals(by_search)["generated"][0] == 1 and totals(by_search)["fermenting"][0] == 0
    assert totals(by_period)["generated"][0] == 0 and totals(by_period)["fermenting"][0] == 1


def test_an_inverted_period_is_rejected(auth_client, estate):
    response = auth_client(estate.owner).get(
        "/api/lots/summary", {"from": "2026-10-20", "to": "2026-10-01"}
    )

    assert response.status_code == 400


def test_counts_only_what_the_account_reaches(auth_client, estate):
    foreman = totals(auth_client(estate.foreman).get("/api/lots/summary"))
    other = totals(auth_client(make_producer_owner(ProducerFactory())).get("/api/lots/summary"))

    assert foreman["generated"][0] == 1 and foreman["fermenting"][0] == 0
    assert all(count == 0 for count, _ in other.values())


def test_the_technical_account_counts_everyone_or_one_producer(auth_client, estate):
    LotFactory()
    client = auth_client(UserFactory(is_superuser=True))

    everyone = totals(client.get("/api/lots/summary"))
    one = totals(client.get("/api/lots/summary", {"producer": str(estate.producer.pk)}))

    assert everyone["generated"][0] == 2
    assert one["generated"][0] == 1


def test_the_association_and_a_user_without_the_permission_are_refused(auth_client, estate):
    plain = make_delegate(estate.producer, ["harvests.view_harvest"], farm=estate.farm_a)

    assert auth_client(make_administrator()).get("/api/lots/summary").status_code == 403
    assert auth_client(plain).get("/api/lots/summary").status_code == 403
