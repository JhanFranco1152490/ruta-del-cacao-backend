"""El código QR con la semilla: el lote vendido de La Esperanza tiene el suyo y su página pública
no muestra al comprador, los precios ni a nadie; queda un lote clasificado sin QR para generarlo en
vivo, y el descartado completo no lo admite.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

import json

import pytest

from apps.accounts.models import User
from apps.demo_data.catalog import DEMO_FARM, DEMO_PRODUCER_EMAIL
from apps.demo_data.seed import seed_demo_data
from apps.lots.choices import LotStatus
from apps.lots.models import Lot, LotQrCode

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    seed_demo_data()


def _farm_lots():
    return Lot.objects.filter(harvest__plot__farm__name=DEMO_FARM)


def _sold_lot():
    return (
        _farm_lots()
        .filter(sale_lines__isnull=False, sale_lines__sale__voided_at__isnull=True)
        .distinct()
        .order_by("code")
        .first()
    )


def test_the_sold_lot_has_its_qr_code_and_nothing_private_on_its_page(anonymous_client, seeded):
    lot = _sold_lot()
    qr = LotQrCode.objects.get(lot=lot)
    buyers = {line.sale.buyer.name for line in lot.sale_lines.select_related("sale__buyer")}
    producer = lot.harvest.plot.farm.producer

    response = anonymous_client.get(f"/api/public/lots/{qr.token}")

    assert response.status_code == 200
    data = response.data
    assert data["origin"]["farm"] == DEMO_FARM
    assert data["origin"]["variety"] == lot.harvest.variety.name
    assert [stage["kind"] for stage in data["stages"]] == [
        "harvest",
        "fermentation",
        "drying",
        "evaluation",
        "classification",
        "stock_entry",
    ]
    assert data["quality"]["well_fermented_pct"] is not None
    body = json.dumps(data, ensure_ascii=False)
    for private in (
        *buyers,
        producer.first_name,
        producer.member_code,
        lot.code,
        lot.harvest.collector.first_name,
    ):
        assert private and private not in body, private


def test_a_classified_lot_is_left_without_qr_code_to_generate_it_live(auth_client, seeded):
    lot = _farm_lots().filter(status=LotStatus.CLASSIFIED, qr_code__isnull=True).first()
    owner = User.objects.get(email=DEMO_PRODUCER_EMAIL)

    response = auth_client(owner).post(f"/api/lots/{lot.pk}/qr")

    assert response.status_code == 201


def test_the_discarded_lot_does_not_admit_one(auth_client, seeded):
    lot = _farm_lots().get(status=LotStatus.DISCARDED)
    owner = User.objects.get(email=DEMO_PRODUCER_EMAIL)

    response = auth_client(owner).post(f"/api/lots/{lot.pk}/qr")

    assert (response.status_code, response.data["code"]) == (409, "lot_not_classified")


def test_an_invented_token_finds_nothing(anonymous_client, seeded):
    assert anonymous_client.get("/api/public/lots/Inventado123456_").status_code == 404


def test_seeding_again_keeps_the_same_qr_code(seeded):
    token = LotQrCode.objects.get(lot=_sold_lot()).token

    seed_demo_data()

    assert list(LotQrCode.objects.values_list("token", flat=True)) == [token]
