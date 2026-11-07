"""La bodega en La Esperanza: lo que deja la semilla y la demostración por la API.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.demo_data.catalog import DEMO_FARM, DEMO_QUALITY_EMAIL
from apps.demo_data.seed import seed_demo_data
from apps.farms.models import Farm
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.warehouse.models import StockBalance, StockEntry, StockExit, Warehouse

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    seed_demo_data()


def demo_lots(status):
    return Lot.objects.filter(harvest__plot__farm__name=DEMO_FARM, status=status)


def counts():
    return (
        Warehouse.objects.count(),
        StockEntry.objects.count(),
        StockBalance.objects.count(),
        StockExit.objects.count(),
        Lot.objects.count(),
    )


def test_every_farm_of_the_demo_producer_has_its_main_warehouse(seeded):
    esperanza = Farm.objects.get(name=DEMO_FARM)

    producer_farms = Farm.objects.filter(producer=esperanza.producer)
    assert producer_farms.count() > 1
    for farm in producer_farms:
        assert Warehouse.objects.filter(
            farm=farm, name="Bodega principal", is_active=True
        ).exists()


def test_the_seed_leaves_lots_to_enter_and_lots_in_the_warehouse(seeded):
    assert demo_lots(LotStatus.CLASSIFIED).count() == 1
    assert demo_lots(LotStatus.IN_WAREHOUSE).count() == 2


def test_one_stored_lot_has_a_sample_and_a_voided_exit(seeded):
    exits = StockExit.objects.filter(lot__harvest__plot__farm__name=DEMO_FARM)

    sample = exits.get(reason="sample")
    assert (sample.grade, sample.quantity_kg, sample.voided_at) == ("g1", Decimal("2.0"), None)
    voided = exits.exclude(voided_at__isnull=True).get()
    assert voided.lot == sample.lot
    assert voided.void_reason


def test_one_stored_lot_has_a_grade_that_ran_out(seeded):
    depleted = StockBalance.objects.get(
        lot__harvest__plot__farm__name=DEMO_FARM, quantity_kg=Decimal("0.0")
    )

    assert depleted.grade == "g2"
    others = StockBalance.objects.filter(lot=depleted.lot).exclude(pk=depleted.pk)
    assert others.get().quantity_kg > 0


def test_the_stock_matches_the_movements(seeded):
    for entry in StockEntry.objects.all():
        for grade, entered in (("g1", entry.g1_kg), ("g2", entry.g2_kg)):
            taken = sum(
                exit_.quantity_kg
                for exit_ in StockExit.objects.filter(
                    lot=entry.lot, grade=grade, voided_at__isnull=True
                )
            )
            balance = StockBalance.objects.get(lot=entry.lot, grade=grade)
            assert balance.quantity_kg == entered - taken


def test_running_it_again_adds_nothing(seeded):
    before = counts()

    seed_demo_data()

    assert counts() == before


def test_using_the_demo_lots_brings_them_back(seeded):
    esperanza = Farm.objects.get(name=DEMO_FARM)
    # Se usa lo que quedaba para la demostración en vivo: el Clasificado se ingresa y el stock se
    # saca por completo.
    inspector = User.objects.get(email=DEMO_QUALITY_EMAIL)
    from apps.warehouse.services.entry import register_entry
    from apps.warehouse.services.exits import remove_stock

    lot = demo_lots(LotStatus.CLASSIFIED).get()
    warehouse = Warehouse.objects.get(farm=esperanza, name="Bodega principal")
    register_entry(
        inspector,
        lot.pk,
        {
            "expected_lot_version": lot.version,
            "entry_date": timezone.localdate(),
            "warehouse_id": warehouse.pk,
            "location": "Estante 9",
        },
    )
    for balance in StockBalance.objects.filter(lot__harvest__plot__farm=esperanza):
        if balance.quantity_kg > 0:
            remove_stock(
                inspector,
                Lot.objects.get(pk=balance.lot_id),
                balance.grade,
                balance.quantity_kg,
                exit_date=timezone.localdate(),
                reason="reprocessing",
            )
    assert not StockBalance.objects.filter(
        lot__harvest__plot__farm=esperanza, quantity_kg__gt=0
    ).exists()
    assert demo_lots(LotStatus.CLASSIFIED).count() == 0

    seed_demo_data()

    assert demo_lots(LotStatus.CLASSIFIED).count() == 1
    assert StockBalance.objects.filter(
        lot__harvest__plot__farm=esperanza, quantity_kg__gt=0
    ).exists()


def test_the_live_demo_works_by_the_api(auth_client, seeded):
    inspector = User.objects.get(email=DEMO_QUALITY_EMAIL)
    client = auth_client(inspector)
    lot = demo_lots(LotStatus.CLASSIFIED).get()
    warehouse = Warehouse.objects.get(farm__name=DEMO_FARM, name="Bodega principal")

    entered = client.post(
        f"/api/stock/{lot.pk}/entry",
        {
            "expected_lot_version": lot.version,
            "entry_date": str(timezone.localdate()),
            "warehouse_id": str(warehouse.pk),
            "location": "Estante 4",
        },
        format="json",
    )
    assert entered.status_code == 201, entered.data
    too_much = client.post(
        f"/api/stock/{lot.pk}/exits",
        {
            "grade": "g1",
            "quantity_kg": "9999.0",
            "exit_date": str(timezone.localdate()),
            "reason": "sample",
        },
        format="json",
    )
    assert (too_much.status_code, too_much.data["code"]) == (400, "stock_insufficient")
    taken = client.post(
        f"/api/stock/{lot.pk}/exits",
        {
            "grade": "g1",
            "quantity_kg": "3.0",
            "exit_date": str(timezone.localdate()),
            "reason": "sample",
        },
        format="json",
    )
    assert taken.status_code == 201, taken.data
    voided = client.post(
        f"/api/stock/{lot.pk}/exits/{taken.data['exits'][0]['id']}/void",
        {"reason": "Se registró dos veces"},
        format="json",
    )
    assert voided.status_code == 200, voided.data
    assert {b["grade"]: b["quantity_kg"] for b in voided.data["balances"]}["g1"] == "90.0"
