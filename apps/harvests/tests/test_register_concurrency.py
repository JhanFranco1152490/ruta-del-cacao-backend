import uuid
from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.tests.factories import FarmFactory
from apps.harvests.models import Harvest, HarvestAuditEvent
from apps.harvests.services.create import create_harvest
from apps.harvests.tests.factories import characterized_plot
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_two_simultaneous_syncs_of_the_same_harvest_create_it_once():
    producer = ProducerFactory()
    farm = FarmFactory(producer=producer)
    plot = characterized_plot(farm=farm, area_hectares=Decimal("2.00"))
    foreman = grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))
    data = {
        "id": uuid.uuid4(),
        "plot_id": plot.pk,
        "harvest_date": date(2026, 10, 1),
        "green_weight_kg": Decimal("80.0"),
        "variety_id": plot.characterization.plantings.first().variety_id,
        "collector_id": foreman.pk,
    }

    results = run_in_parallel(lambda _: create_harvest(foreman, dict(data)), [1, 2])

    assert sorted(created for _, created in results) == [False, True]
    assert Harvest.objects.count() == 1
    assert HarvestAuditEvent.objects.count() == 1
