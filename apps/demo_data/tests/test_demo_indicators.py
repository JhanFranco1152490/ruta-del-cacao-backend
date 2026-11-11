"""Los paneles de indicadores con la semilla: los dos tienen qué mostrar, y el de la asociación,
más de una finca de más de un productor.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.demo_data.catalog import DEMO_ADMIN_EMAIL, DEMO_PRODUCER_EMAIL, SECOND_FARM
from apps.demo_data.seed import seed_demo_data
from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.sales.models import Sale
from apps.warehouse.models import StockEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    seed_demo_data()


def last_year():
    today = timezone.localdate()
    return {"from": str(today - timedelta(days=365)), "to": str(today)}


def second_farm():
    return Farm.objects.get(name=SECOND_FARM)


def test_the_second_farm_has_a_harvest_a_stored_lot_and_a_sale(seeded):
    farm = second_farm()

    assert farm.producer.email != DEMO_PRODUCER_EMAIL
    assert Harvest.objects.filter(plot__farm=farm).count() == 2
    assert StockEntry.objects.filter(lot__harvest__plot__farm=farm).count() == 1
    sale = Sale.objects.get(farm=farm)
    assert sale.voided_at is None
    assert sale.created_by.producer_id == farm.producer_id


def test_seeding_again_adds_nothing_to_the_second_farm(seeded):
    farm = second_farm()
    before = (
        Harvest.objects.filter(plot__farm=farm).count(),
        Sale.objects.filter(farm=farm).count(),
    )

    seed_demo_data()

    after = (
        Harvest.objects.filter(plot__farm=farm).count(),
        Sale.objects.filter(farm=farm).count(),
    )
    assert after == before


def test_the_producer_panel_has_every_section(seeded, auth_client):
    owner = User.objects.get(email=DEMO_PRODUCER_EMAIL)

    response = auth_client(owner).get("/api/indicators/producer", last_year())

    assert response.status_code == 200
    data = response.json()
    assert float(data["production"]["green_kg"]) > 0
    assert float(data["production"]["dry_kg"]) > 0
    assert data["quality"]["g1_pct"] is not None
    assert float(data["inventory"]["total_kg"]) > 0
    assert float(data["sales"]["sold_kg"]) > 0
    # Solo su unidad productiva: la finca del segundo productor no aparece.
    farm_ids = {row["farm_id"] for row in data["production"]["plots"]}
    assert str(second_farm().pk) not in farm_ids


def test_the_association_panel_has_farms_of_two_producers(seeded, auth_client):
    administrator = User.objects.get(email=DEMO_ADMIN_EMAIL)

    response = auth_client(administrator).get("/api/indicators/association", last_year())

    assert response.status_code == 200
    data = response.json()
    assert data["totals"]["producers"] >= 2
    [row] = [row for row in data["farms"] if row["farm_id"] == str(second_farm().pk)]
    assert float(row["green_kg"]) > 0
    assert row["g1_pct"] is not None
    assert float(row["sold_kg"]) > 0
