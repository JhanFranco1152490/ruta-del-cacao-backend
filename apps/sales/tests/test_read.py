from datetime import date

import pytest

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.buyers.tests.factories import BuyerFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.producers.tests.factories import ProducerFactory

from .helpers import month_of, sale_with_lines

pytestmark = pytest.mark.django_db

URL = "/api/sales"
NOVEMBER = date(2026, 11, 15)
WINDOW = month_of(NOVEMBER)


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer, number=1)


@pytest.fixture
def plot(farm):
    return characterized_plot(farm=farm)


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def sale(farm, plot):
    return sale_with_lines(
        farm,
        plot=plot,
        sale_date=NOVEMBER,
        number=12,
        lines=(("g1", "150.0", 18500), ("g2", "40.0", 15000)),
        notes="Despacho en camión",
    )


def detail(sale) -> str:
    return f"{URL}/{sale.pk}"


def ids(response) -> list[str]:
    return [row["id"] for row in response.data["results"]]


# --- Sesión y permisos ---


def test_reading_needs_a_session(anonymous_client, sale):
    assert anonymous_client.get(URL, WINDOW).status_code == 401
    assert anonymous_client.get(detail(sale)).status_code == 401


def test_the_association_does_not_read_sales(auth_client, sale):
    client = auth_client(make_administrator())

    assert client.get(URL, WINDOW).status_code == 403
    assert client.get(detail(sale)).status_code == 403


def test_without_the_permission_it_is_forbidden(auth_client, producer, farm, sale):
    stranger = make_delegate(producer, ["warehouse.view_stock"], farm=farm)

    assert auth_client(stranger).get(URL, WINDOW).status_code == 403


def test_the_sales_manager_reads_the_sales_of_its_farms(auth_client, producer, farm, sale):
    manager = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(SALES_MANAGER))

    assert ids(auth_client(manager).get(URL, WINDOW)) == [str(sale.pk)]
    assert auth_client(manager).get(detail(sale)).status_code == 200


# --- Ficha ---


def test_the_detail_has_the_documented_shape(auth_client, owner, sale):
    row = auth_client(owner).get(detail(sale)).data

    assert set(row) == {
        "id",
        "code",
        "farm",
        "buyer",
        "sale_date",
        "notes",
        "lines",
        "g1_kg",
        "g2_kg",
        "total",
        "invoice",
        "status",
        "created_at",
        "created_by",
        "voided",
        "version",
    }
    assert row["code"] == "V-0012"
    assert row["farm"] == {"id": str(sale.farm.pk), "code": "F01", "name": sale.farm.name}
    assert row["buyer"] == {
        "id": str(sale.buyer.pk),
        "name": sale.buyer.name,
        "buyer_type": sale.buyer.buyer_type,
        "is_active": True,
    }
    assert (row["g1_kg"], row["g2_kg"], row["total"]) == ("150.0", "40.0", 3_375_000)
    assert (row["status"], row["voided"], row["invoice"]) == ("registered", None, None)
    assert row["notes"] == "Despacho en camión"
    assert row["created_by"]["id"] == str(sale.created_by.pk)


def test_each_line_has_its_lot_amounts_and_subtotal(auth_client, owner, sale):
    # Las líneas van por código de lote; aquí cada una es de un lote distinto, con el consecutivo
    # de la fábrica, así que se comparan por calibre.
    response = auth_client(owner).get(detail(sale))
    lines = sorted(response.data["lines"], key=lambda line: line["grade"])

    assert [(line["grade"], line["quantity_kg"], line["price_per_kg"]) for line in lines] == [
        ("g1", "150.0", 18500),
        ("g2", "40.0", 15000),
    ]
    assert [line["subtotal"] for line in lines] == [2_775_000, 600_000]
    assert set(lines[0]["lot"]) == {"id", "code"}


def test_a_voided_sale_says_who_voided_it_and_why(auth_client, owner, farm):
    voided = sale_with_lines(farm, sale_date=NOVEMBER, voided=True)

    row = auth_client(owner).get(detail(voided)).data

    assert row["status"] == "voided"
    assert row["voided"]["reason"] == "Error de digitación"
    assert row["voided"]["voided_by"]["id"] == str(voided.voided_by.pk)


def test_another_producers_sale_does_not_exist(auth_client, owner):
    foreign = sale_with_lines(FarmFactory(), sale_date=NOVEMBER)

    assert auth_client(owner).get(detail(foreign)).status_code == 404


# --- Lista ---


def test_the_list_is_paginated_without_lines_and_newest_first(auth_client, owner, farm, plot):
    older = sale_with_lines(farm, plot=plot, sale_date=date(2026, 11, 3), number=1)
    same_day_first = sale_with_lines(farm, plot=plot, sale_date=NOVEMBER, number=2)
    same_day_second = sale_with_lines(farm, plot=plot, sale_date=NOVEMBER, number=3)

    response = auth_client(owner).get(URL, WINDOW)

    assert response.status_code == 200
    assert {"count", "next", "previous", "results"} <= set(response.data)
    assert ids(response) == [str(same_day_second.pk), str(same_day_first.pk), str(older.pk)]
    row = response.data["results"][0]
    assert "lines" not in row
    assert (row["g1_kg"], row["total"]) == ("150.0", 2_775_000)


def test_the_period_is_required_and_limited(auth_client, owner):
    client = auth_client(owner)

    assert client.get(URL).status_code == 400
    response = client.get(URL, {"from": "2026-01-01", "to": "2027-01-02"})
    assert response.status_code == 400
    assert "to" in response.data["fields"]


def test_only_the_sales_of_the_period_are_listed(auth_client, owner, farm, sale):
    sale_with_lines(farm, sale_date=date(2026, 10, 31))

    assert ids(auth_client(owner).get(URL, WINDOW)) == [str(sale.pk)]


def test_the_list_filters_by_buyer_farm_status_and_number(auth_client, owner, producer, farm):
    other_farm = FarmFactory(producer=producer, number=2)
    buyer = BuyerFactory(producer=producer)
    by_buyer = sale_with_lines(farm, sale_date=NOVEMBER, buyer=buyer, number=7)
    in_other_farm = sale_with_lines(other_farm, sale_date=NOVEMBER, number=8)
    voided = sale_with_lines(farm, sale_date=NOVEMBER, number=19, voided=True)
    client = auth_client(owner)

    assert ids(client.get(URL, {**WINDOW, "buyer": str(buyer.pk)})) == [str(by_buyer.pk)]
    assert ids(client.get(URL, {**WINDOW, "farm": str(other_farm.pk)})) == [str(in_other_farm.pk)]
    assert ids(client.get(URL, {**WINDOW, "status": "voided"})) == [str(voided.pk)]
    assert str(voided.pk) not in ids(client.get(URL, {**WINDOW, "status": "registered"}))
    assert len(ids(client.get(URL, WINDOW))) == 3
    assert ids(client.get(URL, {**WINDOW, "search": "V-0019"})) == [str(voided.pk)]
    assert ids(client.get(URL, {**WINDOW, "search": "7"})) == [str(by_buyer.pk)]


def test_the_list_does_not_query_once_per_sale(
    auth_client, owner, farm, plot, django_assert_max_num_queries
):
    for number in range(1, 6):
        sale_with_lines(farm, plot=plot, sale_date=NOVEMBER, number=number)
    client = auth_client(owner)
    client.get(URL, WINDOW)

    with django_assert_max_num_queries(10):
        response = client.get(URL, WINDOW)

    assert len(ids(response)) == 5


def test_the_technical_account_sees_every_producer_or_the_one_it_names(auth_client, sale):
    other = sale_with_lines(FarmFactory(), sale_date=NOVEMBER)
    client = auth_client(UserFactory(is_superuser=True))

    assert set(ids(client.get(URL, WINDOW))) == {str(sale.pk), str(other.pk)}
    named = client.get(URL, {**WINDOW, "producer": str(other.producer_id)})
    assert ids(named) == [str(other.pk)]


# --- Resumen ---


def test_the_summary_adds_the_registered_sales_of_the_filters(auth_client, owner, farm, sale):
    sale_with_lines(farm, sale_date=NOVEMBER, lines=(("g1", "10.0", 20000),), voided=True)
    sale_with_lines(farm, sale_date=date(2026, 10, 1))

    response = auth_client(owner).get(f"{URL}/summary", WINDOW)

    assert response.status_code == 200
    assert response.data == {"total": 3_375_000, "g1_kg": "150.0", "g2_kg": "40.0", "sales": 1}


def test_the_summary_of_nothing_is_zero(auth_client, owner):
    response = auth_client(owner).get(f"{URL}/summary", WINDOW)

    assert response.data == {"total": 0, "g1_kg": "0.0", "g2_kg": "0.0", "sales": 0}
