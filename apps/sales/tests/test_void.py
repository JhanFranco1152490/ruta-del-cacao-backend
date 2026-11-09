from decimal import Decimal

import pytest

from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate
from apps.sales.models import Sale, SaleAuditEvent
from apps.warehouse.models import StockBalance, StockExit

from .helpers import Market

pytestmark = pytest.mark.django_db

URL = "/api/sales"


@pytest.fixture
def market():
    return Market()


@pytest.fixture
def sale(auth_client, market):
    """Una venta registrada por los servicios: 150,0 kg de G1 y 40,0 de G2 del mismo lote."""
    body = market.body(
        market.line(market.lot, "g1", "150.0", 18500),
        market.line(market.lot, "g2", "40.0", 15000),
    )
    response = auth_client(market.owner).post(URL, body, format="json")
    assert response.status_code == 201, response.data
    return Sale.objects.get(pk=response.data["id"])


def balance(lot, grade="g1"):
    return StockBalance.objects.get(lot=lot, grade=grade).quantity_kg


def void(client, sale, reason="El comprador canceló", version=None):
    body = {"reason": reason, "expected_version": version or sale.version}
    return client.post(f"{URL}/{sale.pk}/void", body, format="json")


def test_voiding_gives_the_kilograms_back_and_keeps_the_sale(auth_client, market, sale):
    assert (balance(market.lot), balance(market.lot, "g2")) == (Decimal("100.0"), Decimal("15.2"))

    response = void(auth_client(market.owner), sale)

    assert response.status_code == 200, response.data
    assert (balance(market.lot), balance(market.lot, "g2")) == (
        Decimal("250.0"),
        Decimal("55.2"),
    )
    assert response.data["status"] == "voided"
    assert response.data["voided"]["reason"] == "El comprador canceló"
    assert response.data["voided"]["voided_by"]["id"] == str(market.owner.pk)
    assert response.data["version"] == 2
    assert len(response.data["lines"]) == 2


def test_the_sale_exits_are_voided_and_stay_in_the_history(auth_client, market, sale):
    void(auth_client(market.owner), sale)

    exits = StockExit.objects.filter(lot=market.lot, reason="sale")
    assert exits.count() == 2
    assert all(exit.voided_at is not None for exit in exits)
    assert {exit.void_reason for exit in exits} == {"El comprador canceló"}


def test_voiding_leaves_its_event(auth_client, market, sale):
    void(auth_client(market.owner), sale)

    event = SaleAuditEvent.objects.get(sale=sale, action="voided")
    assert (event.actor, event.version) == (market.owner, 2)


def test_a_voided_sale_is_not_voided_again(auth_client, market, sale):
    client = auth_client(market.owner)
    void(client, sale)

    response = void(client, sale, version=2)

    assert response.status_code == 409
    assert response.data["code"] == "sale_voided"
    assert balance(market.lot) == Decimal("250.0")


def test_a_stale_version_answers_with_the_current_sale(auth_client, market, sale):
    response = void(auth_client(market.owner), sale, version=5)

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["id"] == str(sale.pk)
    assert balance(market.lot) == Decimal("100.0")


@pytest.mark.parametrize("reason", ["", "   ", "x" * 301])
def test_the_reason_is_required_and_short(auth_client, market, sale, reason):
    response = void(auth_client(market.owner), sale, reason=reason)

    assert response.status_code == 400
    assert "reason" in response.data["fields"]


def test_the_number_is_not_reused_after_voiding(auth_client, market, sale):
    client = auth_client(market.owner)
    void(client, sale)

    response = client.post(URL, market.body(), format="json")

    assert response.data["code"] == "V-0002"


def test_the_stock_is_what_entered_minus_the_exits_in_force_after_selling_and_voiding(
    auth_client, market, sale
):
    client = auth_client(market.owner)
    client.post(URL, market.body(market.line(market.lot, "g1", "30.0", 18000)), format="json")
    void(client, sale)

    for grade, entered in (("g1", Decimal("250.0")), ("g2", Decimal("55.2"))):
        in_force = sum(
            (
                exit.quantity_kg
                for exit in StockExit.objects.filter(
                    lot=market.lot, grade=grade, voided_at__isnull=True
                )
            ),
            Decimal("0"),
        )
        assert balance(market.lot, grade) == entered - in_force
    assert balance(market.lot) == Decimal("220.0")


def test_the_sales_manager_voids_sales(auth_client, market, sale):
    manager = grant_role(
        UserFactory(producer=market.producer, farm=market.farm), get_system_role(SALES_MANAGER)
    )

    assert void(auth_client(manager), sale).status_code == 200


def test_voiding_needs_the_permission_and_the_farm(auth_client, anonymous_client, market, sale):
    viewer = make_delegate(market.producer, ["sales.view_sale"], farm=market.farm)
    elsewhere = make_delegate(market.producer, ["sales.void_sale"], farm=market.other_farm)

    assert void(anonymous_client, sale).status_code == 401
    assert void(auth_client(viewer), sale).status_code == 403
    assert void(auth_client(elsewhere), sale).status_code == 404
    assert balance(market.lot) == Decimal("100.0")
