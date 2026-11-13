from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.producers.tests.factories import ProducerFactory

from .helpers import PERIOD, at, classify, discard_whole, dry, harvest, sell, stock

pytestmark = pytest.mark.django_db

URL = "/api/indicators/producer"
PANEL = "indicators.view_producer_indicators"


class Unit:
    """Un productor con dos fincas y cifras en todas las fuentes, dentro del primer trimestre."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.owner = make_producer_owner(self.producer)
        self.farm_a = FarmFactory(producer=self.producer, name="La Esperanza")
        self.farm_b = FarmFactory(producer=self.producer, name="El Mirador")
        self.river = characterized_plot(
            farm=self.farm_a, name="Lote del río", area_hectares=Decimal("2.50")
        )
        self.hill = characterized_plot(
            farm=self.farm_a, name="La loma", area_hectares=Decimal("1.50")
        )
        self.top = characterized_plot(farm=self.farm_b, name=None, area_hectares=Decimal("1.00"))
        dry(harvest(self.river, date(2026, 1, 10), "400.0"), "136.0")
        harvest(self.river, date(2026, 2, 5), "220.0")
        dry(harvest(self.top, date(2026, 3, 1), "100.0"), "30.0")
        classify(self.river, "290.0", "70.0", "20.0", at(2026, 2, 20, 9))
        stock(self.river, "g1", "120.0")
        stock(self.river, "g2", "35.0")
        sell(self.river, date(2026, 1, 15), ("g1", "150.0", 18500), ("g2", "40.0", 15000))
        sell(self.top, date(2026, 3, 10), ("g1", "20.0", 18500))


@pytest.fixture
def unit():
    return Unit()


def panel(client, **params):
    response = client.get(URL, {**PERIOD, **params})
    assert response.status_code == 200, response.content
    return response.json()


def plot_row(plot, green, dry_kg, green_ha, dry_ha):
    return {
        "plot_id": str(plot.pk),
        "plot_code": plot.code,
        "plot_name": plot.name or "",
        "farm_id": str(plot.farm_id),
        "farm_code": plot.farm.code,
        "farm_name": plot.farm.name,
        "is_active": plot.is_active,
        "area_hectares": str(plot.area_hectares),
        "green_kg": green,
        "dry_kg": dry_kg,
        "green_kg_per_hectare": green_ha,
        "dry_kg_per_hectare": dry_ha,
    }


def test_the_panel_shows_every_section_of_the_unit(auth_client, unit):
    data = panel(auth_client(unit.owner))

    assert data["period"] == {"from": "2026-01-01", "to": "2026-03-31"}
    assert data["production"] == {
        "green_kg": "720.0",
        "dry_kg": "166.0",
        "green_kg_not_dried": "220.0",
        "area_hectares": "5.00",
        "green_kg_per_hectare": "144.0",
        "dry_kg_per_hectare": "33.2",
        "plots": [
            # Por finca y por código: el río es P01 y la loma, P02.
            plot_row(unit.river, "620.0", "136.0", "248.0", "54.4"),
            plot_row(unit.hill, "0.0", "0.0", "0.0", "0.0"),
            plot_row(unit.top, "100.0", "30.0", "100.0", "30.0"),
        ],
        "months": [
            {"month": "2026-01", "green_kg": "400.0", "dry_kg": "136.0"},
            {"month": "2026-02", "green_kg": "220.0", "dry_kg": "0.0"},
            {"month": "2026-03", "green_kg": "100.0", "dry_kg": "30.0"},
        ],
    }
    assert data["quality"] == {
        "classified_kg": "380.0",
        "g1_kg": "290.0",
        "g2_kg": "70.0",
        "discard_kg": "20.0",
        "g1_pct": "76.3",
        "g2_pct": "18.4",
        "discard_pct": "5.3",
        "lots_classified": 1,
        "lots_discarded": 0,
    }
    assert data["inventory"] == {
        "g1_kg": "120.0",
        "g2_kg": "35.0",
        "total_kg": "155.0",
        "farms": [
            {
                "farm_id": str(unit.farm_a.pk),
                "farm_code": unit.farm_a.code,
                "farm_name": "La Esperanza",
                "g1_kg": "120.0",
                "g2_kg": "35.0",
            }
        ],
    }
    assert data["sales"] == {
        "sold_kg": "210.0",
        "g1_kg": "170.0",
        "g2_kg": "40.0",
        "sales": 2,
        "months": [
            {"month": "2026-01", "sold_kg": "190.0"},
            {"month": "2026-02", "sold_kg": "0.0"},
            {"month": "2026-03", "sold_kg": "20.0"},
        ],
    }


def test_a_whole_discard_counts_in_the_quality_shares(auth_client, unit):
    discard_whole(unit.top, "20.0", at(2026, 3, 2, 9))

    quality = panel(auth_client(unit.owner))["quality"]

    assert (quality["classified_kg"], quality["discard_kg"]) == ("400.0", "40.0")
    assert (quality["g1_pct"], quality["discard_pct"]) == ("72.5", "10.0")
    assert quality["lots_discarded"] == 1


def test_new_records_show_in_the_next_request(auth_client, unit):
    client = auth_client(unit.owner)
    before = panel(client)

    harvest(unit.hill, date(2026, 3, 20), "50.0")
    classify(unit.hill, "10.0", "0.0", "0.0", at(2026, 3, 21, 9))
    stock(unit.hill, "g1", "10.0")
    sell(unit.hill, date(2026, 3, 22), ("g1", "5.0", 18500))
    after = panel(client)

    assert (before["production"]["green_kg"], after["production"]["green_kg"]) == (
        "720.0",
        "770.0",
    )
    assert after["quality"]["classified_kg"] == "390.0"
    assert after["inventory"]["g1_kg"] == "130.0"
    assert after["sales"]["sold_kg"] == "215.0"


def test_another_producer_does_not_show(auth_client, unit):
    other = characterized_plot(area_hectares=Decimal("9.00"))
    harvest(other, date(2026, 2, 1), "999.0")
    stock(other, "g1", "999.0")
    sell(other, date(2026, 2, 2), ("g1", "999.0", 18500))

    data = panel(auth_client(unit.owner))

    assert data["production"]["green_kg"] == "720.0"
    assert str(other.pk) not in {row["plot_id"] for row in data["production"]["plots"]}
    assert data["inventory"]["total_kg"] == "155.0"
    assert data["sales"]["sold_kg"] == "210.0"


def test_an_employee_sees_only_the_farms_it_works_on(auth_client, unit):
    employee = make_delegate(unit.producer, [PANEL], farm=unit.farm_b)

    data = panel(auth_client(employee))

    assert [row["plot_id"] for row in data["production"]["plots"]] == [str(unit.top.pk)]
    assert data["production"]["green_kg"] == "100.0"
    assert data["quality"]["classified_kg"] == "0.0"
    assert data["inventory"]["farms"] == []
    assert data["sales"]["sold_kg"] == "20.0"


def test_one_farm_narrows_the_panel(auth_client, unit):
    data = panel(auth_client(unit.owner), farm=str(unit.farm_b.pk))

    assert [row["plot_id"] for row in data["production"]["plots"]] == [str(unit.top.pk)]
    assert data["production"]["area_hectares"] == "1.00"
    assert data["sales"]["sold_kg"] == "20.0"


@pytest.mark.parametrize("whose", ["another producer", "an employee elsewhere"])
def test_a_farm_out_of_reach_does_not_exist(auth_client, unit, whose):
    if whose == "another producer":
        client, farm = auth_client(unit.owner), FarmFactory()
    else:
        client = auth_client(make_delegate(unit.producer, [PANEL], farm=unit.farm_b))
        farm = unit.farm_a

    response = client.get(URL, {**PERIOD, "farm": str(farm.pk)})

    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_the_producer_cannot_choose_another_producer(auth_client, unit):
    other = characterized_plot()
    harvest(other, date(2026, 2, 1), "999.0")

    data = panel(auth_client(unit.owner), producer=str(other.farm.producer_id))

    assert data["production"]["green_kg"] == "720.0"


def test_the_technical_account_sees_everything_or_one_producer(auth_client, unit):
    other = characterized_plot()
    harvest(other, date(2026, 2, 1), "80.0")
    client = auth_client(UserFactory(is_superuser=True))

    assert panel(client)["production"]["green_kg"] == "800.0"
    assert panel(client, producer=str(unit.producer.pk))["production"]["green_kg"] == "720.0"


def test_a_unit_without_records_shows_zeros_and_no_shares(auth_client):
    producer = ProducerFactory()
    plot = characterized_plot(farm=FarmFactory(producer=producer), area_hectares=Decimal("2.00"))

    data = panel(auth_client(make_producer_owner(producer)))

    production = data["production"]
    assert (production["green_kg"], production["dry_kg"], production["area_hectares"]) == (
        "0.0",
        "0.0",
        "2.00",
    )
    assert production["green_kg_per_hectare"] == "0.0"
    assert [row["plot_id"] for row in production["plots"]] == [str(plot.pk)]
    assert data["quality"]["g1_pct"] is None
    assert data["inventory"] == {"g1_kg": "0.0", "g2_kg": "0.0", "total_kg": "0.0", "farms": []}
    assert data["sales"]["months"][0] == {"month": "2026-01", "sold_kg": "0.0"}


def test_without_any_plot_the_per_hectare_figures_are_null(auth_client):
    producer = ProducerFactory()
    FarmFactory(producer=producer)

    production = panel(auth_client(make_producer_owner(producer)))["production"]

    assert (production["area_hectares"], production["green_kg_per_hectare"]) == ("0.00", None)


def test_an_inactive_plot_counts_only_with_harvests_in_the_period(auth_client, unit):
    unit.hill.is_active = False
    unit.hill.save(update_fields=["is_active"])
    retired = characterized_plot(farm=unit.farm_b, area_hectares=Decimal("4.00"), is_active=False)
    harvest(retired, date(2026, 2, 1), "80.0")

    production = panel(auth_client(unit.owner))["production"]

    plot_ids = [row["plot_id"] for row in production["plots"]]
    assert str(unit.hill.pk) not in plot_ids
    assert str(retired.pk) in plot_ids
    # 2,50 + 1,00 + 4,00
    assert production["area_hectares"] == "7.50"


@pytest.mark.parametrize(
    "period",
    [
        {"from": "2026-03-31", "to": "2026-01-01"},
        {"from": "2026-01-01", "to": "2027-01-02"},
        {"from": "2026-01-01"},
    ],
)
def test_an_invalid_period_is_rejected(auth_client, unit, period):
    response = auth_client(unit.owner).get(URL, period)

    assert (response.status_code, response.json()["code"]) == (400, "validation_error")


def test_a_period_of_366_days_is_accepted(auth_client, unit):
    response = auth_client(unit.owner).get(URL, {"from": "2026-01-01", "to": "2027-01-01"})

    assert response.status_code == 200
    assert len(response.json()["production"]["months"]) == 13


@pytest.mark.parametrize("account", ["association", "employee without the permission"])
def test_without_the_permission_the_panel_is_forbidden(auth_client, unit, account):
    if account == "association":
        user = make_administrator()
    else:
        user = make_delegate(unit.producer, ["farms.view_farm"], farm=unit.farm_a)

    response = auth_client(user).get(URL, PERIOD)

    assert response.status_code == 403


def test_the_panel_does_not_query_once_per_farm_or_plot(auth_client, unit):
    client = auth_client(unit.owner)
    with CaptureQueriesContext(connection) as small:
        panel(client)
    for _ in range(3):
        farm = FarmFactory(producer=unit.producer)
        plot = characterized_plot(farm=farm)
        harvest(plot, date(2026, 2, 1), "10.0")
        sell(plot, date(2026, 2, 2), ("g1", "1.0", 18500))
        stock(plot, "g2", "1.0")

    with CaptureQueriesContext(connection) as large:
        panel(client)

    assert len(large) == len(small)
