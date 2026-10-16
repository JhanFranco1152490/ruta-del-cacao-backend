import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.exceptions import HarvestAlreadyInLot
from apps.lots.models import Lot
from apps.lots.services.create import create_lot
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db(transaction=True)


def foreman_and_plot():
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    foreman = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))
    return foreman, characterized_plot(farm=farm)


def attempt(action):
    try:
        return action()
    except HarvestAlreadyInLot as error:
        return error


def test_simultaneous_lots_of_the_same_plot_and_day_get_different_consecutives():
    foreman, plot = foreman_and_plot()
    harvests = [HarvestFactory(plot=plot) for _ in range(4)]

    results = run_in_parallel(
        lambda harvest: create_lot(foreman, {"harvest_id": harvest.pk}), harvests
    )

    codes = sorted(lot.code for lot, _ in results)
    assert [code.rsplit("-", 1)[1] for code in codes] == ["1", "2", "3", "4"]
    assert len(set(codes)) == 4


def test_simultaneous_requests_for_the_same_harvest_leave_a_single_lot():
    foreman, plot = foreman_and_plot()
    harvest = HarvestFactory(plot=plot)

    results = run_in_parallel(
        lambda _: attempt(lambda: create_lot(foreman, {"harvest_id": harvest.pk})), [1, 2, 3]
    )

    created = [result for result in results if isinstance(result, tuple)]
    refused = [result for result in results if isinstance(result, HarvestAlreadyInLot)]
    assert len(created) == 1 and len(refused) == 2
    assert Lot.objects.count() == 1
