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

URL = "/api/indicators/association"


class Association:
    """Dos productores: uno con dos fincas con datos y otra sin nada en el periodo, y otro con
    una finca."""

    def __init__(self):
        self.laura = ProducerFactory(first_name="Laura", last_name="Méndez")
        self.marcos = ProducerFactory(first_name="Marcos", last_name="Villamizar")
        self.esperanza = FarmFactory(
            producer=self.laura, name="La Esperanza", municipality_code="54498"
        )
        self.mirador = FarmFactory(producer=self.laura, name="El Mirador")
        self.empty = FarmFactory(producer=self.laura, name="Sin datos")
        self.palmar = FarmFactory(producer=self.marcos, name="El Palmar")
        river = characterized_plot(farm=self.esperanza)
        top = characterized_plot(farm=self.mirador)
        palm = characterized_plot(farm=self.palmar)
        characterized_plot(farm=self.empty)
        dry(harvest(river, date(2026, 1, 10), "400.0"), "136.0")
        harvest(river, date(2026, 2, 5), "220.0")
        harvest(palm, date(2026, 3, 1), "900.0")
        classify(river, "290.0", "70.0", "20.0", at(2026, 2, 20, 9))
        discard_whole(palm, "50.0", at(2026, 3, 5, 9))
        stock(river, "g1", "120.0")
        sell(river, date(2026, 1, 15), ("g1", "150.0", 18500), ("g2", "40.0", 15000))
        # Solo una venta: El Mirador entra al panel por ella, sin cosechas en el periodo.
        sell(top, date(2026, 3, 10), ("g1", "20.0", 18500))
        self.administrator = make_administrator()


@pytest.fixture
def association():
    return Association()


def panel(client, **params):
    response = client.get(URL, {**PERIOD, **params})
    assert response.status_code == 200, response.content
    return response.json()


def farm_row(farm, **figures):
    return {
        "farm_id": str(farm.pk),
        "farm_code": farm.code,
        "farm_name": farm.name,
        "municipality_code": farm.municipality_code,
        "producer": {
            "id": str(farm.producer.pk),
            "member_code": farm.producer.member_code,
            "first_name": farm.producer.first_name,
            "last_name": farm.producer.last_name,
        },
        **figures,
    }


NO_QUALITY = {
    "classified_kg": "0.0",
    "g1_kg": "0.0",
    "g2_kg": "0.0",
    "discard_kg": "0.0",
    "g1_pct": None,
    "g2_pct": None,
    "discard_pct": None,
}


def test_the_panel_consolidates_by_farm_with_its_totals(auth_client, association):
    data = panel(auth_client(association.administrator))

    assert data["period"] == {"from": "2026-01-01", "to": "2026-03-31"}
    assert data["totals"] == {
        "producers": 2,
        "farms": 3,
        "green_kg": "1520.0",
        "dry_kg": "136.0",
        "classified_kg": "430.0",
        "g1_kg": "290.0",
        "g2_kg": "70.0",
        "discard_kg": "70.0",
        "g1_pct": "67.4",
        "g2_pct": "16.3",
        "discard_pct": "16.3",
        "sold_kg": "210.0",
    }
    assert data["months"] == [
        {"month": "2026-01", "green_kg": "400.0", "dry_kg": "136.0", "sold_kg": "190.0"},
        {"month": "2026-02", "green_kg": "220.0", "dry_kg": "0.0", "sold_kg": "0.0"},
        {"month": "2026-03", "green_kg": "900.0", "dry_kg": "0.0", "sold_kg": "20.0"},
    ]
    assert data["farms"] == [
        farm_row(
            association.palmar,
            green_kg="900.0",
            dry_kg="0.0",
            classified_kg="50.0",
            g1_kg="0.0",
            g2_kg="0.0",
            discard_kg="50.0",
            g1_pct="0.0",
            g2_pct="0.0",
            discard_pct="100.0",
            sold_kg="0.0",
        ),
        farm_row(
            association.esperanza,
            green_kg="620.0",
            dry_kg="136.0",
            classified_kg="380.0",
            g1_kg="290.0",
            g2_kg="70.0",
            discard_kg="20.0",
            g1_pct="76.3",
            g2_pct="18.4",
            discard_pct="5.3",
            sold_kg="190.0",
        ),
        farm_row(association.mirador, green_kg="0.0", dry_kg="0.0", **NO_QUALITY, sold_kg="20.0"),
    ]


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def test_there_is_nothing_by_plot_by_lot_or_of_the_stock(auth_client, association):
    keys = set(_keys(panel(auth_client(association.administrator))))

    assert not {key for key in keys if key.startswith(("plot", "lot", "inventory", "stock"))}
    assert not {"plots", "area_hectares", "lots_classified", "lots_discarded"} & keys


def test_a_farm_without_figures_in_the_period_is_left_out(auth_client, association):
    farm_ids = [row["farm_id"] for row in panel(auth_client(association.administrator))["farms"]]

    assert str(association.empty.pk) not in farm_ids


def test_a_farm_of_an_inactive_producer_with_figures_stays(auth_client, association):
    association.marcos.status = "inactive"
    association.marcos.save(update_fields=["status"])

    farm_ids = [row["farm_id"] for row in panel(auth_client(association.administrator))["farms"]]

    assert str(association.palmar.pk) in farm_ids


def test_farms_with_the_same_green_kg_order_by_name(auth_client):
    for name in ("Zarzal", "Arenal"):
        harvest(characterized_plot(farm=FarmFactory(name=name)), date(2026, 2, 1), "10.0")

    names = [row["farm_name"] for row in panel(auth_client(make_administrator()))["farms"]]

    assert names == ["Arenal", "Zarzal"]


def test_an_association_without_figures_shows_zeros(auth_client):
    data = panel(auth_client(make_administrator()))

    assert data["farms"] == []
    assert (data["totals"]["producers"], data["totals"]["farms"]) == (0, 0)
    assert data["totals"]["green_kg"] == "0.0"
    assert data["totals"]["g1_pct"] is None
    assert len(data["months"]) == 3


def test_the_technical_account_also_sees_the_association_panel(auth_client, association):
    data = panel(auth_client(UserFactory(is_superuser=True)))

    assert data["totals"]["farms"] == 3


@pytest.mark.parametrize("account", ["producer", "employee with the producer panel"])
def test_producer_accounts_cannot_see_the_association_panel(auth_client, association, account):
    if account == "producer":
        user = make_producer_owner(association.laura)
    else:
        user = make_delegate(
            association.laura,
            ["indicators.view_producer_indicators"],
            farm=association.esperanza,
        )

    assert auth_client(user).get(URL, PERIOD).status_code == 403


def test_an_invalid_period_is_rejected(auth_client, association):
    response = auth_client(association.administrator).get(
        URL, {"from": "2026-03-31", "to": "2026-01-01"}
    )

    assert (response.status_code, response.json()["code"]) == (400, "validation_error")


def test_the_panel_does_not_query_once_per_farm(auth_client, association):
    client = auth_client(association.administrator)
    with CaptureQueriesContext(connection) as small:
        panel(client)
    for _ in range(3):
        plot = characterized_plot(farm=FarmFactory())
        harvest(plot, date(2026, 2, 1), "10.0")
        classify(plot, "1.0", "0.0", "0.0", at(2026, 2, 2, 9))
        sell(plot, date(2026, 2, 3), ("g1", "1.0", 18500))

    with CaptureQueriesContext(connection) as large:
        panel(client)

    assert len(large) == len(small)
    assert Decimal(panel(client)["totals"]["green_kg"]) == Decimal("1550.0")
