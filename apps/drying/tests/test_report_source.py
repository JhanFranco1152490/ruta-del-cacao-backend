from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.common.contracts.reports import DryingResult, report_source
from apps.drying.tests.factories import DryingProcessFactory

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")


def finished(**fields):
    return DryingProcessFactory(
        started_at=datetime(2026, 2, 1, 8, 0, tzinfo=BOGOTA),
        ended_at=datetime(2026, 2, 9, 23, 30, tzinfo=BOGOTA),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal("40.5"),
        yield_pct=Decimal("33.8"),
        total_sun_hours=Decimal("40.0"),
        **fields,
    )


def test_a_finished_drying_gives_its_local_end_date_dry_kg_and_yield(django_assert_num_queries):
    drying = finished()

    with django_assert_num_queries(1):
        rows = report_source("drying_results")([drying.lot_id])

    assert rows == [
        DryingResult(
            lot_id=drying.lot_id,
            ended_on=date(2026, 2, 9),
            dry_kg=Decimal("40.5"),
            yield_pct=Decimal("33.8"),
        )
    ]


def test_a_drying_in_progress_and_other_lots_do_not_count():
    running = DryingProcessFactory()
    finished()

    assert report_source("drying_results")([running.lot_id]) == []


def test_no_lots_no_rows(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert report_source("drying_results")([]) == []
