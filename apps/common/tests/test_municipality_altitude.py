import hashlib

from apps.common.municipality_altitude import (
    ALTITUDE_MARGIN_M,
    ALTITUDE_RANGES,
    altitude_range_for,
)
from apps.common.territorial import MUNICIPALITIES_BY_CODE


def test_every_municipality_of_the_department_has_a_range():
    assert set(ALTITUDE_RANGES) == set(MUNICIPALITIES_BY_CODE)


def test_the_range_of_the_terrain_is_widened_by_the_margin():
    # Cúcuta: de 51 a 1547 m.
    assert altitude_range_for("54001") == (0, 1547 + ALTITUDE_MARGIN_M)
    # Un municipio de montaña conserva el margen en los dos lados. Silos: de 2060 a 4256 m.
    assert altitude_range_for("54743") == (2060 - ALTITUDE_MARGIN_M, 4256 + ALTITUDE_MARGIN_M)


def test_the_minimum_never_goes_below_sea_level():
    # Puerto Santander va de 43 a 72 m: con el margen el mínimo sería -57, y se queda en 0.
    assert altitude_range_for("54553") == (0, 72 + ALTITUDE_MARGIN_M)


def test_a_code_that_is_not_a_municipality_has_no_range():
    assert altitude_range_for("99999") is None


def test_the_ranges_are_coherent():
    assert all(minimum < maximum for minimum, maximum in ALTITUDE_RANGES.values())


# La misma tabla y el mismo margen viven copiados en la aplicación web, que avisa con ellos
# mientras se escribe. Los dos repos fijan esta misma huella: si cambia la tabla o el margen, esta
# prueba falla y obliga a actualizar la huella en ambos lados a la vez.
SHARED_TABLE_FINGERPRINT = "b430c1a23646da285ea354451dc3139b3f95649f1836a4292ffcbb8d9e4778cc"


def test_the_table_matches_the_copy_the_web_app_ships():
    lines = [f"margin:{ALTITUDE_MARGIN_M}"] + [
        f"{code}:{minimum}-{maximum}"
        for code, (minimum, maximum) in sorted(ALTITUDE_RANGES.items())
    ]
    assert hashlib.sha256("\n".join(lines).encode()).hexdigest() == SHARED_TABLE_FINGERPRINT
