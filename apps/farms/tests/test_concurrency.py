import uuid

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.tests.concurrency import run_in_parallel
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.services import create_farm
from apps.farms.tests.factories import farm_data
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_two_simultaneous_syncs_of_the_same_farm_create_it_once():
    owner = UserFactory(producer=ProducerFactory())
    data = farm_data(id=uuid.uuid4())

    results = run_in_parallel(lambda _: create_farm(owner, dict(data)), [1, 2])

    assert sorted(created for _, created in results) == [False, True]
    assert {farm.pk for farm, _ in results} == {data["id"]}
    assert Farm.objects.count() == 1
    assert FarmAuditEvent.objects.count() == 1
