"""La historia de los lotes con la semilla: el vendido, el descartado, el clasificado con descarte
y el que fermenta tienen sus etapas en orden; una venta anulada sale marcada; el capataz de La
Esperanza no alcanza un lote de Villa Rosa, y La Esperanza tiene una parcela sin lotes.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

import pytest
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import User
from apps.common.contracts.lot_history import STAGE_KINDS
from apps.demo_data.catalog import DEMO_FOREMAN_EMAIL, DEMO_PRODUCER_EMAIL
from apps.demo_data.seed import seed_demo_data
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.plots.models import Plot

pytestmark = pytest.mark.django_db

DEMO_FARM = "La Esperanza"
OTHER_FARM = "Villa Rosa"


@pytest.fixture
def seeded():
    seed_demo_data()


def _owner():
    return User.objects.get(email=DEMO_PRODUCER_EMAIL)


def _history(auth_client, lot, account=None):
    response = auth_client(account or _owner()).get(f"/api/lots/{lot.pk}/history")
    assert response.status_code == 200, response.data
    return response.data


def _kinds(history):
    return [stage["kind"] for stage in history["stages"]]


def _in_process_order(kinds):
    # La historia sigue el orden del proceso: el tipo de cada etapa nunca va antes que el de la
    # anterior.
    positions = [STAGE_KINDS.index(kind) for kind in kinds]
    return positions == sorted(positions)


def _farm_lots():
    return Lot.objects.filter(harvest__plot__farm__name=DEMO_FARM)


def test_a_sold_lot_goes_from_the_harvest_to_its_sales(auth_client, seeded):
    # Con líneas de venta: sin esa condición, `voided_at__isnull` también da los lotes sin ventas.
    lot = (
        _farm_lots()
        .filter(sale_lines__isnull=False, sale_lines__sale__voided_at__isnull=True)
        .distinct()
        .first()
    )

    history = _history(auth_client, lot)
    kinds = _kinds(history)

    assert kinds[:2] == ["harvest", "lot_created"]
    assert {"fermentation", "drying", "evaluation", "classification", "stock_entry"} <= set(kinds)
    assert kinds[-1] == "sale"
    assert _in_process_order(kinds)
    assert history["current"]["sold_kg"] != "0.0"


def test_the_whole_discard_shows_its_date_quantity_and_reason(auth_client, seeded):
    lot = _farm_lots().get(status=LotStatus.DISCARDED)

    history = _history(auth_client, lot)
    discard = history["stages"][-1]

    assert discard["kind"] == "discard"
    assert discard["occurred_on"]
    assert discard["discard"]["quantity_kg"]
    assert discard["discard"]["reason"] == "mold"
    assert history["current"]["status"] == "discarded"


def test_the_partial_discard_is_in_the_classification(auth_client, seeded):
    lot = _farm_lots().filter(classification__discard_kg__gt=0).first()

    history = _history(auth_client, lot)
    [classification] = [s for s in history["stages"] if s["kind"] == "classification"]

    assert classification["classification"]["discard_kg"] != "0.0"
    assert classification["classification"]["discard_reason"] == "mold"


def test_a_fermenting_lot_shows_only_what_it_has_so_far(auth_client, seeded):
    lot = _farm_lots().filter(status=LotStatus.FERMENTING).first()

    history = _history(auth_client, lot)

    assert _kinds(history) == ["harvest", "lot_created", "fermentation"]
    assert history["stages"][-1]["fermentation"]["ended_at"] is None
    assert history["current"]["sold_kg"] is None


def test_the_voided_sale_is_marked_in_the_history_of_its_lot(auth_client, seeded):
    lot = _farm_lots().filter(sale_lines__sale__voided_at__isnull=False).distinct().first()

    sales = [s["sale"] for s in _history(auth_client, lot)["stages"] if s["kind"] == "sale"]

    assert any(sale["voided_at"] is not None and sale["void_reason"] for sale in sales)


def test_the_foreman_does_not_reach_a_lot_of_another_producer(auth_client, seeded):
    foreign = Lot.objects.filter(harvest__plot__farm__name=OTHER_FARM).first()
    foreman = User.objects.get(email=DEMO_FOREMAN_EMAIL)

    response = auth_client(foreman).get(f"/api/lots/{foreign.pk}/history")

    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_la_esperanza_has_plots_without_lots(seeded):
    # L-02 tiene ficha y se puede cosechar en vivo; L-03 no tiene ficha.
    plots = Plot.objects.filter(farm__name=DEMO_FARM, name__in=["L-02", "L-03"])

    assert plots.count() == 2
    assert not Lot.objects.filter(harvest__plot__in=plots).exists()


def test_seeding_again_keeps_the_same_histories(auth_client, seeded):
    lot = _farm_lots().get(status=LotStatus.DISCARDED)
    before = _kinds(_history(auth_client, lot))

    seed_demo_data()

    assert _kinds(_history(auth_client, lot)) == before


def test_every_fermented_lot_was_formed_before_its_fermentation(seeded):
    late = _farm_lots().filter(
        fermentation__isnull=False, created_at__gte=F("fermentation__started_at")
    )

    assert not late.exists()


def test_seeding_again_fixes_a_lot_formed_after_its_fermentation(seeded):
    lot = _farm_lots().filter(fermentation__isnull=False).first()
    Lot.objects.filter(pk=lot.pk).update(created_at=timezone.now())

    seed_demo_data()

    lot.refresh_from_db()
    assert lot.created_at < lot.fermentation.started_at
    assert timezone.localdate(lot.created_at) >= lot.harvest.harvest_date
