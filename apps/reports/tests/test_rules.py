from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from apps.common.contracts.indicators import IndicatorPeriod
from apps.reports.rules import (
    kg_sum,
    labeled,
    period_text,
    place_order,
    producer_text,
    reason_text,
)


def test_a_code_goes_with_its_name_or_alone():
    assert labeled("F02", "La Esperanza") == "F02 · La Esperanza"
    assert labeled("P05", "") == "P05"


def test_a_producer_is_named_by_its_member_code_and_full_name():
    assert producer_text("000123", "Rosa", "Quintero") == "000123 · Rosa Quintero"


def test_the_period_is_written_day_first():
    period = IndicatorPeriod(date(2026, 1, 1), date(2026, 11, 12))

    assert period_text(period) == "01/01/2026 – 12/11/2026"


def test_places_order_by_the_number_of_their_codes():
    def place(farm, plot):
        return SimpleNamespace(farm_code=farm, plot_code=plot)

    places = [place("F100", "P01"), place("F02", "P10"), place("F02", "P09")]

    assert sorted(places, key=place_order) == [places[2], places[1], places[0]]


def test_kg_add_up_with_one_decimal():
    assert kg_sum([Decimal("1.25"), Decimal("2.0")]) == Decimal("3.3")
    assert kg_sum([]) == Decimal("0.0")


def test_a_reason_goes_with_its_detail_when_there_is_one():
    assert reason_text("Otro", "Se mojó") == "Otro: Se mojó"
    assert reason_text("Moho", "") == "Moho"
    assert reason_text("", "") == ""
