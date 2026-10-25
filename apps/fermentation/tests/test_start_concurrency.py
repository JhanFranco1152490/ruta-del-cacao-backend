import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.exceptions import ApiError
from apps.common.tests.concurrency import run_in_parallel
from apps.fermentation.models import FermentationProcess, FermentationTurn
from apps.fermentation.services.start import start_fermentation
from apps.fermentation.services.turns import record_turn

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


def test_the_same_turn_sent_from_two_phones_at_once_is_saved_once():
    place = Farmstead()
    started_at = (timezone.now() - timedelta(hours=60)).replace(second=0, microsecond=0)
    start_fermentation(
        place.foreman,
        {
            "lot_id": place.lot.pk,
            "facility_id": place.box.pk,
            "started_at": started_at,
            "responsible_id": place.foreman.pk,
        },
    )
    turned_at = started_at + timedelta(hours=48)

    def send(_):
        data = {
            "id": uuid.uuid4(),
            "turned_at": turned_at,
            "temperature_c": Decimal("45.0"),
            "ph": Decimal("4.90"),
        }
        return attempt(lambda: record_turn(place.foreman, place.lot.pk, data))

    results = run_in_parallel(send, [1, 2])

    refused = [result for result in results if isinstance(result, ApiError)]
    assert [error.default_code for error in refused] == ["duplicate_turn_time"]
    assert FermentationTurn.objects.count() == 1
