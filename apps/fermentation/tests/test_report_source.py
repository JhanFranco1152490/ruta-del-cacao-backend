from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.common.contracts.reports import FermentationDates, report_source
from apps.fermentation.tests.factories import FermentationProcessFactory

pytestmark = pytest.mark.django_db

BOGOTA = ZoneInfo("America/Bogota")


def test_the_dates_are_local_and_a_running_one_has_no_end(django_assert_num_queries):
    # 23:30 en Bogotá ya es el día siguiente en UTC: la fecha que cuenta es la local.
    done = FermentationProcessFactory(
        started_at=datetime(2026, 2, 1, 23, 30, tzinfo=BOGOTA),
        ended_at=datetime(2026, 2, 7, 23, 30, tzinfo=BOGOTA),
    )
    running = FermentationProcessFactory(started_at=datetime(2026, 2, 10, 8, 0, tzinfo=BOGOTA))
    FermentationProcessFactory()

    with django_assert_num_queries(1):
        rows = report_source("fermentation_dates")([done.lot_id, running.lot_id])

    assert sorted(rows, key=lambda row: row.started_on) == [
        FermentationDates(
            lot_id=done.lot_id, started_on=date(2026, 2, 1), ended_on=date(2026, 2, 7)
        ),
        FermentationDates(lot_id=running.lot_id, started_on=date(2026, 2, 10), ended_on=None),
    ]


def test_no_lots_no_rows(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert report_source("fermentation_dates")([]) == []
