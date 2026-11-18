from datetime import date

import pytest

from apps.reports.exceptions import ReportTooLarge
from apps.reports.services import producer

from .helpers import PERIOD, Estate, generate, harvest

pytestmark = pytest.mark.django_db


def test_the_limit_is_five_thousand_rows():
    assert producer.MAX_ROWS == 5000


def test_a_report_over_the_limit_asks_to_narrow_the_filters(monkeypatch):
    estate = Estate()
    monkeypatch.setattr(producer, "MAX_ROWS", 2)
    for day in (1, 2):
        harvest(estate.rio, date(2026, 2, day), "10.0")

    assert len(generate(estate.owner, type="production", **PERIOD).rows) == 2

    harvest(estate.rio, date(2026, 2, 3), "10.0")
    with pytest.raises(ReportTooLarge) as error:
        generate(estate.owner, type="production", **PERIOD)

    assert error.value.status_code == 400
    assert error.value.default_code == "report_too_large"
