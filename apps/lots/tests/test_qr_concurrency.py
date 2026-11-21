import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.exceptions import LotQrAlreadyExists
from apps.lots.models import LotQrCode
from apps.lots.services.qr import generate_lot_qr
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db(transaction=True)


def attempt(owner, lot_id):
    try:
        return generate_lot_qr(owner, lot_id)
    except LotQrAlreadyExists as error:
        return error


def test_simultaneous_requests_leave_a_single_qr_code():
    producer = ProducerFactory()
    plot = characterized_plot(farm=FarmFactory(producer=producer))
    lot = LotFactory(harvest=HarvestFactory(plot=plot), status=LotStatus.CLASSIFIED)
    owner = make_producer_owner(producer)

    results = run_in_parallel(lambda _: attempt(owner, lot.pk), [1, 2, 3])

    created = [result for result in results if isinstance(result, LotQrCode)]
    refused = [result for result in results if isinstance(result, LotQrAlreadyExists)]
    assert len(created) == 1 and len(refused) == 2
    assert LotQrCode.objects.count() == 1
