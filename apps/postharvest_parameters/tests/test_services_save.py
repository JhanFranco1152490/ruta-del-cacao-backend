from dataclasses import asdict

import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.common.tests.concurrency import run_in_parallel
from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.exceptions import StaleParameters
from apps.postharvest_parameters.models import PostharvestParameters
from apps.postharvest_parameters.services.save import save_parameters
from apps.producers.tests.factories import ProducerFactory


@pytest.mark.django_db(transaction=True)
def test_two_first_saves_at_the_same_time_leave_one_row_and_one_stale_answer():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    def save(day):
        values = {**asdict(DRYING_BASELINE), "slow_duration_day": day}
        try:
            return save_parameters(owner, None, 0, values).version
        except StaleParameters:
            return "stale"

    results = run_in_parallel(save, [9, 10])

    assert sorted(results, key=str) == [1, "stale"]
    assert PostharvestParameters.objects.filter(pk=producer.pk).count() == 1
