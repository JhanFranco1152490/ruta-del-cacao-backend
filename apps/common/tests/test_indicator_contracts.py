from datetime import date

import pytest

from apps.common.contracts import indicators
from apps.common.contracts.indicators import (
    INDICATOR_SOURCES,
    IndicatorPeriod,
    indicator_source,
    register_indicator_source,
)


@pytest.fixture
def empty_registry(monkeypatch):
    # Las apps ya registraron sus fuentes al arrancar: la prueba trabaja sobre un registro propio
    # para no pisarlas.
    monkeypatch.setattr(indicators, "_sources", {})


def test_a_registered_source_is_returned_by_its_name(empty_registry):
    def harvests(farm_ids, period):
        return []

    register_indicator_source("harvests", harvests)

    assert indicator_source("harvests") is harvests


def test_asking_for_a_source_nobody_registered_fails_loudly(empty_registry):
    with pytest.raises(RuntimeError):
        indicator_source("sales")


def test_a_source_outside_the_known_names_cannot_be_registered(empty_registry):
    with pytest.raises(ValueError):
        register_indicator_source("activities", lambda farm_ids, period: [])


def test_the_known_sources_are_the_ones_the_panels_combine():
    assert INDICATOR_SOURCES == {
        "farm_scope",
        "farms",
        "plots",
        "harvests",
        "drying",
        "quality",
        "warehouse",
        "sales",
    }


def test_a_period_within_one_month_has_that_month():
    period = IndicatorPeriod(date(2026, 3, 5), date(2026, 3, 20))

    assert period.months() == ["2026-03"]


def test_a_period_lists_every_month_even_across_the_year():
    period = IndicatorPeriod(date(2025, 11, 30), date(2026, 2, 1))

    assert period.months() == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_a_period_of_366_days_starting_on_the_first_has_thirteen_months():
    period = IndicatorPeriod(date(2026, 1, 1), date(2027, 1, 1))

    assert period.months()[0] == "2026-01"
    assert period.months()[-1] == "2027-01"
    assert len(period.months()) == 13


def test_a_month_key_is_year_and_month():
    assert IndicatorPeriod.month_key(date(2026, 7, 31)) == "2026-07"
