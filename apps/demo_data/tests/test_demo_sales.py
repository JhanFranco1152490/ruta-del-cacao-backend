"""Las ventas en La Esperanza: lo que deja la semilla y la demostración por la API.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.demo_data.catalog import DEMO_FARM, DEMO_SALES_MANAGER_EMAIL
from apps.demo_data.seed import seed_demo_data
from apps.sales.models import Sale
from apps.warehouse.models import StockBalance, StockExit

pytestmark = pytest.mark.django_db

URL = "/api/sales"


@pytest.fixture
def seeded():
    seed_demo_data()


def demo_sales():
    return Sale.objects.filter(farm__name=DEMO_FARM)


def manager():
    return User.objects.get(email=DEMO_SALES_MANAGER_EMAIL)


def test_the_seed_leaves_a_registered_sale_with_its_invoice_and_a_voided_one(seeded):
    registered = demo_sales().get(voided_at__isnull=True)
    voided = demo_sales().get(voided_at__isnull=False)

    assert registered.buyer.name == "Chocolates del Oriente S.A.S."
    assert sorted(registered.lines.values_list("grade", flat=True)) == ["g1", "g2"]
    assert registered.invoice_content_type == "application/pdf"
    assert registered.invoice.read().startswith(b"%PDF-")
    assert voided.void_reason
    assert not voided.invoice
    assert [sale.created_by for sale in (registered, voided)] == [manager(), manager()]


def test_the_sales_went_through_the_warehouse(seeded):
    registered = demo_sales().get(voided_at__isnull=True)
    voided = demo_sales().get(voided_at__isnull=False)

    assert all(line.stock_exit.reason == "sale" for line in registered.lines.all())
    assert all(line.stock_exit.voided_at is None for line in registered.lines.all())
    assert all(line.stock_exit.voided_at is not None for line in voided.lines.all())


def test_running_it_again_adds_no_sale(seeded):
    before = (Sale.objects.count(), StockExit.objects.filter(reason="sale").count())

    seed_demo_data()

    assert (Sale.objects.count(), StockExit.objects.filter(reason="sale").count()) == before


def test_there_is_stock_left_to_sell_live(seeded):
    assert StockBalance.objects.filter(
        lot__harvest__plot__farm__name=DEMO_FARM, grade="g1", quantity_kg__gte=Decimal("20.0")
    ).exists()


def test_the_demonstration_sells_refuses_too_much_and_voids(seeded, auth_client):
    client = auth_client(manager())
    stock = (
        StockBalance.objects.filter(lot__harvest__plot__farm__name=DEMO_FARM, grade="g1")
        .order_by("-quantity_kg")
        .first()
    )
    farm = stock.lot.harvest.plot.farm
    available = stock.quantity_kg
    buyer = client.get(f"{URL}/buyer-options").data["results"][0]

    def body(kilos):
        return {
            "farm_id": str(farm.pk),
            "buyer_id": buyer["id"],
            "sale_date": timezone.localdate().isoformat(),
            "lines": [
                {
                    "lot_id": str(stock.lot_id),
                    "grade": "g1",
                    "quantity_kg": kilos,
                    "price_per_kg": 18500,
                }
            ],
        }

    # El caso negativo: más de lo que hay.
    too_much = client.post(URL, body(f"{available + 1:.1f}"), format="json")
    assert too_much.status_code == 400
    assert too_much.data["code"] == "stock_insufficient"

    sold = client.post(URL, body("10.0"), format="json")
    assert sold.status_code == 201, sold.data
    assert sold.data["total"] == 185_000
    stock.refresh_from_db()
    assert stock.quantity_kg == available - Decimal("10.0")

    voided = client.post(
        f"{URL}/{sold.data['id']}/void",
        {"reason": "Prueba de la demostración", "expected_version": sold.data["version"]},
        format="json",
    )
    assert voided.status_code == 200
    stock.refresh_from_db()
    assert stock.quantity_kg == available
