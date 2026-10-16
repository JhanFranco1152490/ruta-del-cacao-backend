"""Consultar lotes: filtros, búsqueda por parte del código, alcance y detalle."""

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
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


class Estate:
    """Un productor con dos fincas (F01 y F02), cada una con una parcela y un lote."""

    def __init__(self):
        self.producer = ProducerFactory(member_code="PROD-000123")
        self.farm_a = FarmFactory(producer=self.producer, number=1)
        self.farm_b = FarmFactory(producer=self.producer, number=2)
        self.variety_a = CacaoVarietyFactory()
        self.plot_a = characterized_plot(
            variety=self.variety_a, farm=self.farm_a, number=1, area_hectares=Decimal("5.00")
        )
        self.plot_b = characterized_plot(farm=self.farm_b, number=5, area_hectares=Decimal("5.00"))
        self.lot_a = self.lot(self.plot_a, date(2026, 10, 14), "000123-F01-P01-261014-1")
        self.lot_b = self.lot(self.plot_b, date(2026, 10, 20), "000123-F02-P05-261020-1")
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm_a), get_system_role(FOREMAN)
        )

    def lot(self, plot, day, code, **fields):
        harvest = HarvestFactory(plot=plot, harvest_date=day)
        return LotFactory(harvest=harvest, code=code, **fields)


@pytest.fixture
def estate():
    return Estate()


def ids(response):
    return [item["id"] for item in response.data["results"]]


def test_lists_the_lots_most_recent_harvest_first_and_paginated(auth_client, estate):
    response = auth_client(estate.owner).get("/api/lots")

    assert response.status_code == 200
    assert response.data["count"] == 2
    assert ids(response) == [str(estate.lot_b.pk), str(estate.lot_a.pk)]


def test_the_page_size_is_honored(auth_client, estate):
    response = auth_client(estate.owner).get("/api/lots", {"page_size": 1})

    assert len(response.data["results"]) == 1
    assert response.data["next"] is not None


def test_equal_dates_are_ordered_by_code(auth_client, estate):
    later = estate.lot(estate.plot_a, date(2026, 10, 20), "000123-F01-P01-261020-1")

    response = auth_client(estate.owner).get("/api/lots")

    assert ids(response)[:2] == [str(later.pk), str(estate.lot_b.pk)]


def test_filters_by_status(auth_client, estate):
    estate.lot_b.status = LotStatus.FERMENTING
    estate.lot_b.save()

    response = auth_client(estate.owner).get("/api/lots", {"status": "fermenting"})

    assert ids(response) == [str(estate.lot_b.pk)]


def test_filters_by_farm_plot_and_variety(auth_client, estate):
    client = auth_client(estate.owner)

    by_farm = client.get("/api/lots", {"farm": str(estate.farm_b.pk)})
    by_plot = client.get("/api/lots", {"plot": str(estate.plot_a.pk)})
    by_variety = client.get("/api/lots", {"variety": str(estate.variety_a.pk)})

    assert ids(by_farm) == [str(estate.lot_b.pk)]
    assert ids(by_plot) == [str(estate.lot_a.pk)]
    assert ids(by_variety) == [str(estate.lot_a.pk)]


def test_filters_by_the_period_of_the_harvest(auth_client, estate):
    client = auth_client(estate.owner)

    only_first = client.get("/api/lots", {"from": "2026-10-01", "to": "2026-10-14"})
    only_second = client.get("/api/lots", {"from": "2026-10-15"})
    none = client.get("/api/lots", {"to": "2026-09-30"})

    assert ids(only_first) == [str(estate.lot_a.pk)]
    assert ids(only_second) == [str(estate.lot_b.pk)]
    assert ids(none) == []


def test_an_inverted_period_is_rejected(auth_client, estate):
    response = auth_client(estate.owner).get(
        "/api/lots", {"from": "2026-10-20", "to": "2026-10-01"}
    )

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("261014", ["a"]),
        ("F02-P05", ["b"]),
        ("f02-p05", ["b"]),
        ("000123", ["b", "a"]),
        ("-1", ["b", "a"]),
        ("nada", []),
        ("", ["b", "a"]),
    ],
)
def test_searches_by_part_of_the_code_without_case(auth_client, estate, term, expected):
    response = auth_client(estate.owner).get("/api/lots", {"search": term})

    codes = {"a": str(estate.lot_a.pk), "b": str(estate.lot_b.pk)}
    assert ids(response) == [codes[key] for key in expected]


def test_a_search_with_wildcard_characters_is_literal(auth_client, estate):
    assert ids(auth_client(estate.owner).get("/api/lots", {"search": "%"})) == []
    assert ids(auth_client(estate.owner).get("/api/lots", {"search": "_"})) == []


def test_the_foreman_only_sees_the_lots_of_their_farm(auth_client, estate):
    response = auth_client(estate.foreman).get("/api/lots")

    assert ids(response) == [str(estate.lot_a.pk)]


def test_an_employee_without_a_farm_sees_nothing(auth_client, estate):
    nobody = make_delegate(estate.producer, ["lots.view_lot"])

    assert ids(auth_client(nobody).get("/api/lots")) == []


def test_another_producer_sees_none_of_it(auth_client, estate):
    other = make_producer_owner(ProducerFactory())

    assert ids(auth_client(other).get("/api/lots")) == []


def test_the_technical_account_sees_all_and_filters_by_producer(auth_client, estate):
    stranger = LotFactory()
    client = auth_client(UserFactory(is_superuser=True))

    everyone = client.get("/api/lots")
    one = client.get("/api/lots", {"producer": str(estate.producer.pk)})

    assert str(stranger.pk) in ids(everyone) and everyone.data["count"] == 3
    assert set(ids(one)) == {str(estate.lot_a.pk), str(estate.lot_b.pk)}


def test_the_association_and_a_user_without_the_permission_are_refused(auth_client, estate):
    plain = make_delegate(estate.producer, ["harvests.view_harvest"], farm=estate.farm_a)

    assert auth_client(make_administrator()).get("/api/lots").status_code == 403
    assert auth_client(plain).get("/api/lots").status_code == 403


def test_the_list_query_count_does_not_grow_with_the_lots(auth_client, estate):
    client = auth_client(estate.owner)
    with CaptureQueriesContext(connection) as few:
        client.get("/api/lots")
    for day in range(1, 11):
        estate.lot(estate.plot_a, date(2026, 9, day), f"000123-F01-P01-2609{day:02d}-1")

    with CaptureQueriesContext(connection) as many:
        response = client.get("/api/lots", {"page_size": 100})

    assert response.data["count"] == 12
    assert len(many) == len(few)


def test_the_detail_shows_the_origin_of_the_lot(auth_client, estate):
    response = auth_client(estate.owner).get(f"/api/lots/{estate.lot_a.pk}")

    assert response.status_code == 200
    assert response.data["code"] == "000123-F01-P01-261014-1"
    harvest = response.data["harvest"]
    assert harvest["plot"]["code"] == "P01"
    assert harvest["plot"]["farm"]["code"] == "F01"
    assert harvest["variety"]["id"] == str(estate.variety_a.pk)
    assert harvest["collector"]["full_name"]
    assert response.data["producer"]["member_code"] == "PROD-000123"
    assert response.data["green_weight_kg"] == "120.5"


def test_the_detail_of_what_is_out_of_reach_does_not_exist(auth_client, estate):
    foreman = auth_client(estate.foreman)

    assert foreman.get(f"/api/lots/{estate.lot_b.pk}").status_code == 404
    assert foreman.get(f"/api/lots/{LotFactory().pk}").status_code == 404
