"""Generar el código QR de un lote: solo Clasificado o En bodega, y uno solo por lote."""

import uuid

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.exceptions import LotNotClassified, LotNotFound, LotQrAlreadyExists
from apps.lots.models import LotQrCode
from apps.lots.services.qr import generate_lot_qr
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

WITHOUT_QR = [
    LotStatus.GENERATED,
    LotStatus.FERMENTING,
    LotStatus.FERMENTED,
    LotStatus.DRYING,
    LotStatus.DRIED,
    LotStatus.EVALUATED,
    LotStatus.DISCARDED,
]


class Estate:
    def __init__(self):
        self.producer = ProducerFactory()
        self.farm = FarmFactory(producer=self.producer)
        self.plot = characterized_plot(farm=self.farm)
        self.owner = make_producer_owner(self.producer)

    def lot(self, status=LotStatus.CLASSIFIED, farm=None):
        plot = self.plot if farm is None else characterized_plot(farm=farm)
        return LotFactory(harvest=HarvestFactory(plot=plot), status=status)


@pytest.fixture
def estate():
    return Estate()


@pytest.mark.parametrize("status", [LotStatus.CLASSIFIED, LotStatus.IN_WAREHOUSE])
def test_a_classified_or_stored_lot_gets_its_qr_code(estate, status):
    lot = estate.lot(status)

    qr = generate_lot_qr(estate.owner, lot.pk)

    assert qr.lot == lot
    assert qr.created_by == estate.owner
    assert len(qr.token) == 16
    assert LotQrCode.objects.get(lot=lot) == qr


@pytest.mark.parametrize("status", WITHOUT_QR)
def test_a_lot_before_its_classification_or_discarded_gets_none(estate, status):
    lot = estate.lot(status)

    with pytest.raises(LotNotClassified) as refused:
        generate_lot_qr(estate.owner, lot.pk)

    assert refused.value.extra == {"current_status": status}
    assert not LotQrCode.objects.exists()


def test_a_second_qr_code_is_refused_and_the_first_one_stays(estate):
    lot = estate.lot()
    first = generate_lot_qr(estate.owner, lot.pk)

    with pytest.raises(LotQrAlreadyExists):
        generate_lot_qr(estate.owner, lot.pk)

    assert list(LotQrCode.objects.values_list("token", flat=True)) == [first.token]


def test_the_lot_of_another_producer_is_not_found(estate):
    other = Estate()
    lot = other.lot()

    with pytest.raises(LotNotFound):
        generate_lot_qr(estate.owner, lot.pk)

    assert not LotQrCode.objects.exists()


def test_an_employee_does_not_reach_the_lot_of_another_farm(estate):
    other_farm = FarmFactory(producer=estate.producer)
    foreman = grant_role(
        UserFactory(producer=estate.producer, farm=estate.farm), get_system_role(FOREMAN)
    )
    lot = estate.lot(farm=other_farm)

    with pytest.raises(LotNotFound):
        generate_lot_qr(foreman, lot.pk)


def test_an_employee_of_the_farm_generates_it(estate):
    worker = grant_role(
        UserFactory(producer=estate.producer, farm=estate.farm), get_system_role(FOREMAN)
    )

    qr = generate_lot_qr(worker, estate.lot().pk)

    assert qr.created_by == worker


def test_a_lot_that_does_not_exist_is_not_found(estate):
    with pytest.raises(LotNotFound):
        generate_lot_qr(estate.owner, uuid.uuid4())
