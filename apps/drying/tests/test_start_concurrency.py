import pytest
from django.utils import timezone

from apps.common.exceptions import ApiError
from apps.common.tests.concurrency import run_in_parallel
from apps.drying.models import DryingProcess
from apps.drying.services.start import start_drying

from .helpers import Farmstead, fermented_lot


@pytest.mark.django_db(transaction=True)
def test_two_starts_at_the_same_time_in_the_same_dryer_leave_one():
    estate = Farmstead()
    lots = [estate.lot, fermented_lot(estate.plot_a)]

    def begin(lot):
        try:
            start_drying(
                estate.owner,
                {
                    "lot_id": lot.pk,
                    "facility_id": estate.dryer.pk,
                    "started_at": timezone.now(),
                    "entry_moisture_pct": 58,
                    "responsible_id": estate.foreman.pk,
                },
            )
            return "started"
        except ApiError as error:
            return error.default_code

    results = run_in_parallel(begin, lots)

    assert sorted(results) == ["facility_unavailable", "started"]
    assert DryingProcess.objects.count() == 1
