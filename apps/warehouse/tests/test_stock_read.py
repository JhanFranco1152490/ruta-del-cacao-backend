"""Consultar las existencias (HU-39)."""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_administrator, make_delegate
from apps.warehouse.models import StockBalance

from .factories import WarehouseFactory
from .helpers import WarehouseEstate, stored_lot

pytestmark = pytest.mark.django_db

URL = "/api/stock"


@pytest.fixture
def estate():
    """La finca A con tres lotes en bodega: el de siempre (250,0 de G1 y 55,2 de G2 en «Estante
    3»), uno solo de G1 en «Zona A» y uno de G1 y G2 en otra bodega de la misma finca. En B, uno.
    """
    estate = WarehouseEstate()
    estate.second, _ = stored_lot(
        estate.plot_a, estate.warehouse_a, g1="100.0", g2="0.0", location="Zona A"
    )
    estate.annex = WarehouseFactory(farm=estate.farm_a, name="Anexo", name_normalized="anexo")
    estate.third, _ = stored_lot(
        estate.plot_a, estate.annex, g1="40.0", g2="20.0", location="Zona A"
    )
    estate.in_b, _ = stored_lot(
        estate.plot_b, estate.warehouse_b, g1="10.0", g2="5.0", location="Estante 1"
    )
    return estate


def rows(client, **params):
    response = client.get(URL, params)
    assert response.status_code == 200, response.data
    return response.data["results"]


def keys(rows_):
    return {(row["lot"]["id"], row["grade"]) for row in rows_}


# --- CA-01: consulta general ---


def test_every_lot_shows_each_grade_with_its_kilograms_and_place(auth_client, estate):
    result = rows(auth_client(estate.owner))

    assert keys(result) == {
        (str(estate.stored.pk), "g1"),
        (str(estate.stored.pk), "g2"),
        (str(estate.second.pk), "g1"),
        (str(estate.third.pk), "g1"),
        (str(estate.third.pk), "g2"),
        (str(estate.in_b.pk), "g1"),
        (str(estate.in_b.pk), "g2"),
    }
    row = next(r for r in result if r["lot"]["id"] == str(estate.stored.pk) and r["grade"] == "g1")
    assert row["quantity_kg"] == "250.0"
    assert (row["warehouse"]["name"], row["location"]) == ("Bodega A", "Estante 3")
    assert row["farm"]["id"] == str(estate.farm_a.pk)
    assert row["lot"]["code"] == estate.stored.code
    assert row["entry_date"]


def test_the_totals_add_each_grade_of_every_row(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/summary")

    assert response.status_code == 200, response.data
    assert response.data == {"g1_kg": "400.0", "g2_kg": "80.2", "lots": 4}


# --- CA-02: filtros ---


def test_it_filters_by_grade(auth_client, estate):
    result = rows(auth_client(estate.owner), grade="g2")

    assert {row["grade"] for row in result} == {"g2"}
    assert len(result) == 3


def test_it_filters_by_warehouse_and_by_location_and_by_lot_code(auth_client, estate):
    client = auth_client(estate.owner)

    assert keys(rows(client, warehouse=str(estate.annex.pk))) == {
        (str(estate.third.pk), "g1"),
        (str(estate.third.pk), "g2"),
    }
    assert {r["lot"]["id"] for r in rows(client, location="zona")} == {
        str(estate.second.pk),
        str(estate.third.pk),
    }
    assert {r["lot"]["id"] for r in rows(client, search=estate.in_b.code[:6].lower())} >= {
        str(estate.in_b.pk)
    }
    one = rows(client, search=estate.second.code)
    assert {r["lot"]["id"] for r in one} == {str(estate.second.pk)}


def test_the_filters_combine_and_the_totals_follow_them(auth_client, estate):
    client = auth_client(estate.owner)
    params = {"location": "Zona A", "grade": "g1"}

    assert keys(rows(client, **params)) == {
        (str(estate.second.pk), "g1"),
        (str(estate.third.pk), "g1"),
    }
    summary = client.get(f"{URL}/summary", params).data
    assert summary == {"g1_kg": "140.0", "g2_kg": "0.0", "lots": 2}


def test_the_farm_filter_narrows_to_one_farm(auth_client, estate):
    result = rows(auth_client(estate.owner), farm=str(estate.farm_b.pk))

    assert {r["lot"]["id"] for r in result} == {str(estate.in_b.pk)}


# --- CA-03 y CA-04 ---


def test_a_filter_without_matches_is_an_empty_list(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"location": "Sótano"})

    assert response.status_code == 200
    assert (response.data["count"], response.data["results"]) == (0, [])
    summary = auth_client(estate.owner).get(f"{URL}/summary", {"location": "Sótano"}).data
    assert summary == {"g1_kg": "0.0", "g2_kg": "0.0", "lots": 0}


def test_a_grade_that_ran_out_is_not_shown_but_the_other_is(auth_client, estate):
    StockBalance.objects.filter(lot=estate.stored, grade="g1").update(quantity_kg=Decimal("0.0"))

    result = rows(auth_client(estate.owner), search=estate.stored.code)

    assert keys(result) == {(str(estate.stored.pk), "g2")}


def test_a_lot_that_ran_out_of_both_grades_leaves_the_list(auth_client, estate):
    StockBalance.objects.filter(lot=estate.second).update(quantity_kg=Decimal("0.0"))

    assert str(estate.second.pk) not in {r["lot"]["id"] for r in rows(auth_client(estate.owner))}
    assert auth_client(estate.owner).get(f"{URL}/summary").data["lots"] == 3


# --- Orden ---


def test_the_default_order_is_the_most_recent_entry_then_the_code(auth_client, estate):
    result = rows(auth_client(estate.owner))
    dates = [row["entry_date"] for row in result]

    assert dates == sorted(dates, reverse=True)


@pytest.mark.parametrize(
    ("ordering", "key", "reverse"),
    [
        ("quantity", lambda r: Decimal(r["quantity_kg"]), False),
        ("-quantity", lambda r: Decimal(r["quantity_kg"]), True),
        ("location", lambda r: r["location"], False),
        ("grade", lambda r: r["grade"], False),
        ("lot", lambda r: r["lot"]["code"], False),
    ],
)
def test_the_rows_can_be_ordered(auth_client, estate, ordering, key, reverse):
    result = rows(auth_client(estate.owner), ordering=ordering)
    values = [key(row) for row in result]

    assert values == sorted(values, reverse=reverse)


def test_an_unknown_ordering_is_refused(auth_client, estate):
    assert auth_client(estate.owner).get(URL, {"ordering": "farm"}).status_code == 400


def test_the_list_is_paginated(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"page_size": 3})

    assert (response.data["count"], len(response.data["results"])) == (7, 3)
    assert response.data["next"]


# --- Ubicaciones ---


def test_the_locations_are_the_ones_with_stock_in_the_warehouse(auth_client, estate):
    response = auth_client(estate.owner).get(
        f"{URL}/locations", {"warehouse": str(estate.warehouse_a.pk)}
    )

    assert response.status_code == 200, response.data
    assert response.data == {"results": ["Estante 3", "Zona A"]}


def test_the_locations_leave_out_places_that_ran_out(auth_client, estate):
    StockBalance.objects.filter(lot=estate.second).update(quantity_kg=Decimal("0.0"))

    response = auth_client(estate.owner).get(
        f"{URL}/locations", {"warehouse": str(estate.warehouse_a.pk)}
    )

    assert response.data == {"results": ["Estante 3"]}


def test_the_locations_need_a_warehouse(auth_client, estate):
    assert auth_client(estate.owner).get(f"{URL}/locations").status_code == 400


def test_the_locations_of_a_warehouse_out_of_reach_are_empty(auth_client, estate):
    response = auth_client(estate.inspector).get(
        f"{URL}/locations", {"warehouse": str(estate.warehouse_b.pk)}
    )

    assert response.data == {"results": []}


# --- Alcance y permisos ---


def test_it_needs_a_session(anonymous_client, estate):
    for suffix in ("", "/summary", f"/locations?warehouse={estate.warehouse_a.pk}"):
        assert anonymous_client.get(f"{URL}{suffix}").status_code == 401


def test_the_association_has_no_access(auth_client, estate):
    client = auth_client(make_administrator())

    for suffix in ("", "/summary", f"/locations?warehouse={estate.warehouse_a.pk}"):
        assert client.get(f"{URL}{suffix}").status_code == 403


def test_an_employee_sees_only_the_stock_of_its_farm(auth_client, estate):
    result = rows(auth_client(estate.inspector))

    assert {r["farm"]["id"] for r in result} == {str(estate.farm_a.pk)}
    summary = auth_client(estate.inspector).get(f"{URL}/summary").data
    assert summary == {"g1_kg": "390.0", "g2_kg": "75.2", "lots": 3}


def test_an_employee_without_a_farm_sees_nothing(auth_client, estate):
    drifter = make_delegate(estate.producer, ["warehouse.view_stock"])

    assert rows(auth_client(drifter)) == []


def test_another_producer_never_shows_up(auth_client, estate):
    other = WarehouseEstate()

    mine = {r["lot"]["id"] for r in rows(auth_client(estate.owner))}

    assert str(other.stored.pk) not in mine


def test_the_sales_manager_reads_the_stock(auth_client, estate):
    sales = grant_role(
        UserFactory(producer=estate.producer, all_farms=True), get_system_role(SALES_MANAGER)
    )

    assert len(rows(auth_client(sales))) == 7


def test_the_technical_account_chooses_the_producer(auth_client, estate):
    other = WarehouseEstate()
    technical = UserFactory(is_superuser=True, producer=None)
    client = auth_client(technical)

    only_other = rows(client, producer=str(other.producer.pk))

    assert {r["lot"]["id"] for r in only_other} == {str(other.stored.pk)}
    assert len(rows(client)) > len(only_other)


def test_a_delegate_without_view_stock_is_forbidden(auth_client, estate):
    delegate = make_delegate(estate.producer, ["warehouse.register_entry"], farm=estate.farm_a)

    assert auth_client(delegate).get(URL).status_code == 403


def test_the_list_does_not_grow_with_the_rows(auth_client, estate):
    client = auth_client(estate.owner)
    client.get(URL)  # abre la sesión y calienta lo que el primer pedido carga

    def queries(page_size):
        with CaptureQueriesContext(connection) as captured:
            response = client.get(URL, {"page_size": page_size})
        assert response.status_code == 200
        return len(captured)

    assert queries(1) == queries(100)
