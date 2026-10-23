from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.exceptions import ApiError
from apps.common.tests.concurrency import run_in_parallel
from apps.fermentation.models import FermentationProcess
from apps.fermentation.services.start import start_fermentation

from .helpers import Farmstead

pytestmark = pytest.mark.django_db(transaction=True)


def attempt(action):
    try:
        return action()
    except ApiError as error:
        return error


def test_two_lots_started_at_once_in_the_same_box_leave_only_one_inside():
    place = Farmstead()
    lots = [place.lot, place.new_lot(Decimal("100.0"))]

    def start(lot):
        data = {
            "lot_id": lot.pk,
            "facility_id": place.box.pk,
            "started_at": timezone.now() - timedelta(hours=1),
            "responsible_id": place.foreman.pk,
        }
        return attempt(lambda: start_fermentation(place.foreman, data))

    results = run_in_parallel(start, lots)

    refused = [result for result in results if isinstance(result, ApiError)]
    assert len(refused) == 1
    assert refused[0].default_code == "facility_unavailable"
    assert FermentationProcess.objects.count() == 1
    place.box.refresh_from_db()
    assert place.box.current_lot_id in {lot.pk for lot in lots}
