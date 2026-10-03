from apps.common.municipality_altitude import (
    ALTITUDE_MARGIN_M,
    ALTITUDE_RANGES,
    altitude_range_for,
)
from apps.common.territorial import MUNICIPALITIES_BY_CODE


def test_every_municipality_of_the_department_has_a_range():
    assert set(ALTITUDE_RANGES) == set(MUNICIPALITIES_BY_CODE)


def test_the_range_of_the_terrain_is_widened_by_the_margin():
    # Puerto Santander: de 43 a 72 m.
    assert altitude_range_for("54553") == (43 - ALTITUDE_MARGIN_M, 72 + ALTITUDE_MARGIN_M)


def test_a_code_that_is_not_a_municipality_has_no_range():
    assert altitude_range_for("99999") is None


def test_the_ranges_are_coherent():
    assert all(minimum < maximum for minimum, maximum in ALTITUDE_RANGES.values())
