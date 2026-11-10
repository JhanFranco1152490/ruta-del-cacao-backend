from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
)
from apps.buyers.tests.factories import BuyerFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.lots.choices import LotStatus
from apps.sales.exceptions import SaleStockInsufficient
from apps.sales.models import Sale, SaleAuditEvent, SaleCodeSequence
from apps.sales.services import create_sale
from apps.warehouse.models import StockBalance, StockExit

from .helpers import Market

pytestmark = pytest.mark.django_db

URL = "/api/sales"


@pytest.fixture
def market():
    return Market()


def balance(lot, grade="g1"):
    return StockBalance.objects.get(lot=lot, grade=grade).quantity_kg


def post(client, body):
    return client.post(URL, body, format="json")


# --- El caso feliz (HU-43, CA-01) ---


def test_a_sale_takes_out_each_line_and_computes_its_total(auth_client, market):
    body = market.body(
        market.line(market.lot, "g1", "150.0", 18500),
        market.line(market.lot, "g2", "40.0", 15000),
        notes="Despacho en camión",
    )

    response = post(auth_client(market.owner), body)

    assert response.status_code == 201, response.data
    sale = Sale.objects.get()
    assert response["Location"] == f"{URL}/{sale.pk}"
    assert (response.data["code"], response.data["total"]) == ("V-0001", 3_375_000)
    assert (response.data["g1_kg"], response.data["g2_kg"]) == ("150.0", "40.0")
    assert [line["subtotal"] for line in response.data["lines"]] == [2_775_000, 600_000]
    assert (balance(market.lot), balance(market.lot, "g2")) == (Decimal("100.0"), Decimal("15.2"))
    exits = StockExit.objects.filter(lot=market.lot, reason="sale")
    assert exits.count() == 2
    assert {line.stock_exit_id for line in sale.lines.all()} == {exit.pk for exit in exits}
    assert sale.created_by == market.owner
    assert SaleAuditEvent.objects.get(sale=sale).action == "created"


def test_the_lot_stays_in_the_warehouse_also_when_it_is_sold_out(auth_client, market):
    post(auth_client(market.owner), market.body(market.line(market.lot, "g1", "250.0", 18000)))

    market.lot.refresh_from_db()
    assert market.lot.status == LotStatus.IN_WAREHOUSE
    assert balance(market.lot) == Decimal("0.0")


def test_a_sale_can_take_from_several_lots_of_its_farm(auth_client, market):
    body = market.body(
        market.line(market.lot, "g1", "100.0", 18000),
        market.line(market.second_lot, "g1", "50.0", 18000),
    )

    assert post(auth_client(market.owner), body).status_code == 201
    assert (balance(market.lot), balance(market.second_lot)) == (
        Decimal("150.0"),
        Decimal("200.0"),
    )


def test_the_sales_manager_registers_sales(auth_client, market):
    manager = grant_role(
        UserFactory(producer=market.producer, farm=market.farm), get_system_role(SALES_MANAGER)
    )

    assert post(auth_client(manager), market.body()).status_code == 201


# --- El número ---


def test_the_numbers_follow_each_other_per_producer(auth_client, market):
    client = auth_client(market.owner)
    codes = [
        post(client, market.body(market.line(market.lot, "g1", "10.0", 18000))).data["code"]
        for _ in range(3)
    ]
    other = Market()
    first_of_other = post(auth_client(other.owner), other.body()).data["code"]

    assert codes == ["V-0001", "V-0002", "V-0003"]
    assert first_of_other == "V-0001"


# --- Lo que se rechaza ---


def test_more_than_what_is_available_changes_nothing_and_says_which_line(auth_client, market):
    body = market.body(
        market.line(market.lot, "g1", "100.0", 18000),
        market.line(market.lot, "g2", "60.0", 15000),
    )

    response = post(auth_client(market.owner), body)

    assert response.status_code == 400
    assert response.data["code"] == "stock_insufficient"
    assert (response.data["line"], response.data["available_kg"]) == (1, "55.2")
    assert response.data["fields"]["lines"] == ["La cantidad supera lo disponible (55,2 kg)"]
    assert not Sale.objects.exists()
    assert not StockExit.objects.exists()
    assert balance(market.lot) == Decimal("250.0")
    # El número tampoco se consume: la transacción se deshizo entera.
    assert not SaleCodeSequence.objects.filter(producer=market.producer, last_value__gt=0).exists()


def test_a_lot_that_is_not_in_the_warehouse_answers_its_status_and_line(auth_client, market):
    body = market.body(market.line(market.classified, "g1", "10.0", 18000))

    response = post(auth_client(market.owner), body)

    assert response.status_code == 409
    assert response.data["code"] == "lot_invalid_status"
    assert (response.data["current_status"], response.data["line"]) == ("classified", 0)


def test_a_lot_of_another_farm_does_not_exist_for_the_sale(auth_client, market):
    body = market.body(market.line(market.other_farm_lot, "g1", "10.0", 18000))

    response = post(auth_client(market.owner), body)

    assert response.status_code == 404
    assert response.data["line"] == 0
    assert balance(market.other_farm_lot) == Decimal("250.0")


def test_an_inactive_buyer_is_refused(auth_client, market):
    response = post(auth_client(market.owner), market.body(buyer_id=str(market.inactive_buyer.pk)))

    assert response.status_code == 422
    assert response.data["code"] == "buyer_inactive"
    assert "buyer_id" in response.data["fields"]


def test_a_buyer_of_another_producer_does_not_exist(auth_client, market):
    response = post(auth_client(market.owner), market.body(buyer_id=str(BuyerFactory().pk)))

    assert response.status_code == 404


def test_an_inactive_farm_is_refused(auth_client, market):
    Farm.objects.filter(pk=market.farm.pk).update(is_active=False)

    response = post(auth_client(market.owner), market.body())

    assert response.status_code == 422
    assert response.data["code"] == "farm_inactive"


def test_a_farm_of_another_producer_does_not_exist(auth_client, market):
    response = post(auth_client(market.owner), market.body(farm_id=str(FarmFactory().pk)))

    assert response.status_code == 404


def test_a_date_before_the_entry_of_a_lot_is_refused(auth_client, market):
    day_before = market.lot.stock_entry.entry_date - timedelta(days=1)

    response = post(auth_client(market.owner), market.body(sale_date=day_before.isoformat()))

    assert response.status_code == 400
    assert market.lot.code in response.data["fields"]["sale_date"][0]
    assert not Sale.objects.exists()


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"farm_id": None}, "farm_id"),
        ({"buyer_id": None}, "buyer_id"),
        ({"sale_date": None}, "sale_date"),
        ({"sale_date": "2999-01-01"}, "sale_date"),
        ({"notes": "x" * 301}, "notes"),
        ({"lines": []}, "lines"),
        ({"version": 2}, "version"),
    ],
)
def test_invalid_sale_data_is_refused_by_field(auth_client, market, changes, field):
    body = {key: value for key, value in {**market.body(), **changes}.items() if value is not None}

    response = post(auth_client(market.owner), body)

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert field in response.data["fields"]
    assert not Sale.objects.exists()


@pytest.mark.parametrize(
    "line_changes",
    [
        {"quantity_kg": "0.0"},
        {"quantity_kg": "-5.0"},
        {"quantity_kg": "10.25"},
        {"price_per_kg": 0},
        {"price_per_kg": 1_000_001},
        {"price_per_kg": "18500.5"},
        {"grade": "g3"},
        {"lot_id": None},
    ],
)
def test_invalid_lines_are_refused(auth_client, market, line_changes):
    line = {**market.line(market.lot, "g1", "10.0", 18000), **line_changes}
    line = {key: value for key, value in line.items() if value is not None}

    response = post(auth_client(market.owner), market.body(line))

    assert response.status_code == 400
    assert "lines" in response.data["fields"]
    assert balance(market.lot) == Decimal("250.0")


def test_more_than_twenty_lines_are_refused(auth_client, market):
    lines = [market.line(market.lot, "g1", "1.0", 18000) for _ in range(21)]

    response = post(auth_client(market.owner), market.body(*lines))

    assert response.status_code == 400
    assert "lines" in response.data["fields"]


def test_a_lot_and_grade_twice_are_refused(auth_client, market):
    body = market.body(
        market.line(market.lot, "g1", "10.0", 18000),
        market.line(market.lot, "g1", "5.0", 18000),
    )

    response = post(auth_client(market.owner), body)

    assert response.status_code == 400
    assert response.data["fields"]["lines"] == ["Ese lote y calibre ya está en otra línea."]


# --- Permisos y alcance ---


def test_registering_needs_a_session_and_the_permission(auth_client, anonymous_client, market):
    viewer = make_delegate(market.producer, ["sales.view_sale"], farm=market.farm)

    assert post(anonymous_client, market.body()).status_code == 401
    assert post(auth_client(viewer), market.body()).status_code == 403
    assert post(auth_client(make_administrator()), market.body()).status_code == 403


def test_an_employee_does_not_sell_from_another_farm(auth_client, market):
    seller = make_delegate(market.producer, ["sales.add_sale"], farm=market.other_farm)

    assert post(auth_client(seller), market.body()).status_code == 404


def test_the_technical_account_sells_for_any_producer(auth_client, market):
    response = post(auth_client(UserFactory(is_superuser=True)), market.body())

    assert response.status_code == 201
    assert Sale.objects.get().producer == market.producer


# --- Concurrencia ---


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_sales_never_take_more_than_there_is():
    market = Market()

    def attempt(_):
        data = {
            "farm_id": market.farm.pk,
            "buyer_id": market.buyer.pk,
            "sale_date": timezone.localdate(),
            "notes": "",
            "lines": [
                {
                    "lot_id": market.lot.pk,
                    "grade": "g1",
                    "quantity_kg": Decimal("200.0"),
                    "price_per_kg": 18000,
                }
            ],
        }
        try:
            return create_sale(market.owner, data)
        except SaleStockInsufficient as error:
            return error

    results = run_in_parallel(attempt, [1, 2])

    assert sum(isinstance(result, SaleStockInsufficient) for result in results) == 1
    assert balance(market.lot) == Decimal("50.0")
    assert Sale.objects.count() == 1
    assert list(Sale.objects.values_list("number", flat=True)) == [1]


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_sales_of_one_producer_do_not_repeat_a_number():
    market = Market()

    def attempt(lot):
        return create_sale(
            market.owner,
            {
                "farm_id": market.farm.pk,
                "buyer_id": market.buyer.pk,
                "sale_date": timezone.localdate(),
                "notes": "",
                "lines": [
                    {
                        "lot_id": lot.pk,
                        "grade": "g1",
                        "quantity_kg": Decimal("10.0"),
                        "price_per_kg": 18000,
                    }
                ],
            },
        )

    run_in_parallel(attempt, [market.lot, market.second_lot])

    assert sorted(Sale.objects.values_list("number", flat=True)) == [1, 2]


# --- Compradores del formulario ---


def test_the_form_offers_the_active_buyers_of_the_producer_without_their_contact(
    auth_client, market
):
    BuyerFactory()  # de otro productor

    response = auth_client(market.owner).get(f"{URL}/buyer-options")

    assert response.status_code == 200
    assert response.data["results"] == [
        {"id": str(market.buyer.pk), "name": market.buyer.name, "buyer_type": "chocolate_industry"}
    ]


def test_the_buyer_options_need_the_permission_to_register(auth_client, market):
    viewer = make_delegate(market.producer, ["sales.view_sale"], farm=market.farm)

    assert auth_client(viewer).get(f"{URL}/buyer-options").status_code == 403


def test_the_technical_account_gets_the_buyer_options_of_the_producer_it_names(
    auth_client, market
):
    client = auth_client(UserFactory(is_superuser=True))

    response = client.get(f"{URL}/buyer-options", {"producer": str(market.producer.pk)})

    assert [row["id"] for row in response.data["results"]] == [str(market.buyer.pk)]
