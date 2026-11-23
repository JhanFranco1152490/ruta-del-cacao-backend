"""El código QR de un lote por la API: generarlo y verlo en la representación del lote."""

import pytest
from django.test import override_settings

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.models import LotQrCode
from apps.lots.tests.factories import LotFactory, LotQrCodeFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

FRONTEND = "https://app.example.com"
VIEWER = ["harvests.view_harvest", "plots.view_plot", "farms.view_farm", "lots.view_lot"]


class Estate:
    def __init__(self):
        self.producer = ProducerFactory()
        self.farm = FarmFactory(producer=self.producer)
        self.other_farm = FarmFactory(producer=self.producer)
        self.owner = make_producer_owner(self.producer)

    def lot(self, status=LotStatus.CLASSIFIED, farm=None):
        plot = characterized_plot(farm=farm or self.farm)
        return LotFactory(harvest=HarvestFactory(plot=plot), status=status)


@pytest.fixture
def estate():
    return Estate()


def generate(client, lot):
    return client.post(f"/api/lots/{lot.pk}/qr")


@override_settings(FRONTEND_URL=FRONTEND)
def test_the_producer_generates_the_qr_code_of_a_classified_lot(auth_client, estate):
    lot = estate.lot()

    response = generate(auth_client(estate.owner), lot)

    qr = LotQrCode.objects.get(lot=lot)
    assert response.status_code == 201
    assert response.data == {
        "token": qr.token,
        "public_url": f"{FRONTEND}/trazabilidad/{qr.token}",
        "created_at": response.data["created_at"],
    }
    assert response.data["created_at"]


def test_a_lot_that_is_not_classified_is_refused(auth_client, estate):
    lot = estate.lot(LotStatus.EVALUATED)

    response = generate(auth_client(estate.owner), lot)

    assert response.status_code == 409
    assert response.data["code"] == "lot_not_classified"
    assert response.data["current_status"] == "evaluated"


def test_a_second_qr_code_is_refused(auth_client, estate):
    lot = estate.lot()
    client = auth_client(estate.owner)
    generate(client, lot)

    response = generate(client, lot)

    assert (response.status_code, response.data["code"]) == (409, "lot_qr_already_exists")
    assert LotQrCode.objects.count() == 1


def test_an_employee_with_the_permission_generates_only_in_its_farm(auth_client, estate):
    delegate = make_delegate(estate.producer, [*VIEWER, "lots.add_lotqrcode"], farm=estate.farm)
    client = auth_client(delegate)

    assert generate(client, estate.lot()).status_code == 201
    foreign = generate(client, estate.lot(farm=estate.other_farm))
    assert (foreign.status_code, foreign.data["code"]) == (404, "not_found")


def test_seeing_lots_is_not_enough_to_generate(auth_client, estate):
    viewer = make_delegate(estate.producer, VIEWER, farm=estate.farm)

    response = generate(auth_client(viewer), estate.lot())

    assert response.status_code == 403
    assert not LotQrCode.objects.exists()


def test_the_lot_of_another_producer_is_not_found(auth_client, estate):
    response = generate(auth_client(estate.owner), Estate().lot())

    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_the_technical_account_generates_it(auth_client, estate):
    technical = UserFactory(is_superuser=True, is_staff=True)

    assert generate(auth_client(technical), estate.lot()).status_code == 201


def test_without_a_session_it_is_refused(api_client, estate):
    assert generate(api_client, estate.lot()).status_code == 401


@override_settings(FRONTEND_URL=FRONTEND)
def test_the_lot_detail_and_list_bring_the_qr_code(auth_client, estate):
    with_qr = LotQrCodeFactory(lot=estate.lot(LotStatus.IN_WAREHOUSE), token="Xq3k9Lm2Pz7tRw1a")
    without = estate.lot()
    client = auth_client(estate.owner)

    detail = client.get(f"/api/lots/{with_qr.lot.pk}").data["qr"]
    listed = {row["id"]: row["qr"] for row in client.get("/api/lots").data["results"]}

    assert detail["token"] == "Xq3k9Lm2Pz7tRw1a"
    assert detail["public_url"] == f"{FRONTEND}/trazabilidad/Xq3k9Lm2Pz7tRw1a"
    assert client.get(f"/api/lots/{without.pk}").data["qr"] is None
    assert listed == {str(with_qr.lot.pk): detail, str(without.pk): None}


def test_whoever_sees_the_lot_sees_its_qr_code(auth_client, estate):
    qr = LotQrCodeFactory(lot=estate.lot())
    viewer = make_delegate(estate.producer, VIEWER, farm=estate.farm)

    response = auth_client(viewer).get(f"/api/lots/{qr.lot.pk}")

    assert response.data["qr"]["token"] == qr.token
