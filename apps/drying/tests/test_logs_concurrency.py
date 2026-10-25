import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.common.exceptions import ApiError
from apps.common.tests.concurrency import run_in_parallel
from apps.drying.models import DryingLogEntry
from apps.drying.services.logs import record_log
from apps.drying.services.start import start_drying

from .helpers import Farmstead, fermented_lot


@pytest.mark.django_db(transaction=True)
def test_two_phones_sending_the_same_date_at_once_leave_one_log():
    estate = Farmstead()
    lot = fermented_lot(estate.plot_a, actor=estate.owner, hours_ago=120)
    start_day = timezone.localdate() - timedelta(days=3)
    started_at = timezone.make_aware(datetime.combine(start_day, time(14, 0)))
    start_drying(
        estate.owner,
        {
            "lot_id": lot.pk,
            "facility_id": estate.dryer.pk,
            "started_at": started_at,
            "entry_moisture_pct": Decimal("58.0"),
            "responsible_id": estate.foreman.pk,
        },
    )
    second_day = started_at + timedelta(days=1)

    def send(hour):
        try:
            record_log(
                estate.foreman,
                lot.pk,
                {
                    "id": uuid.uuid4(),
                    "measured_at": second_day.replace(hour=hour),
                    "moisture_pct": Decimal("45.0"),
                    "sun_hours": Decimal("5.0"),
                    "turn_count": 0,
                    "weather": "sunny",
                },
            )
            return "created"
        except ApiError as error:
            return error.default_code

    results = run_in_parallel(send, [9, 16])

    assert sorted(results) == ["created", "duplicate_drying_log_date"]
    assert DryingLogEntry.objects.count() == 1
