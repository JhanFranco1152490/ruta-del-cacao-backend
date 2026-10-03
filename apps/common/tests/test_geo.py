import pytest

from apps.common.geo import distance_m, ring_area_m2

# Áreas que da `@turf/area` 7.4 para los mismos anillos. El frontend fija estos mismos valores
# en sus pruebas: si las dos fórmulas se separan, la persona vería al dibujar un área distinta
# de la que el servidor valida.
TURF_REFERENCE = [
    (
        [(-72.5, 7.8), (-72.4990917, 7.8), (-72.4990917, 7.8009044), (-72.5, 7.8009044)],
        10062.912069,
    ),
    (
        [(-72.7321, 8.6429), (-72.73102, 8.64318), (-72.73095, 8.64462), (-72.73228, 8.64441)],
        21891.188770,
    ),
    (
        [
            (-72.5123456, 7.8234567),
            (-72.5101234, 7.8239876),
            (-72.5109876, 7.8251234),
            (-72.5115432, 7.8243210),
            (-72.5126543, 7.8250123),
        ],
        26545.083230,
    ),
]


@pytest.mark.parametrize(("ring", "expected"), TURF_REFERENCE)
def test_ring_area_matches_turf(ring, expected):
    assert ring_area_m2(ring) == pytest.approx(expected, abs=1e-6)


def test_ring_area_does_not_depend_on_the_direction_of_the_ring():
    ring = TURF_REFERENCE[1][0]

    assert ring_area_m2(list(reversed(ring))) == pytest.approx(ring_area_m2(ring))


@pytest.mark.parametrize(
    "ring", [[], [(-72.5, 7.8)], [(-72.5, 7.8), (-72.49, 7.8)]], ids=["0", "1", "2"]
)
def test_ring_area_of_fewer_than_three_points_is_zero(ring):
    assert ring_area_m2(ring) == 0


# Distancias que da `@turf/distance` en metros para los mismos pares de puntos: el frontend mide
# con ella, y el servidor debe dar lo mismo para que el límite a la finca no difiera.
TURF_DISTANCES = [
    ((-72.5, 7.8), (-72.4990917, 7.8009044), 141.86639856041953),
    ((-72.7321, 8.6429), (-72.73228, 8.64441), 169.06655934103796),
    ((-72.5, 7.8), (-72.5, 8.8), 111195.080233533),
]


@pytest.mark.parametrize(("origin", "target", "expected"), TURF_DISTANCES)
def test_distance_matches_turf(origin, target, expected):
    assert distance_m(origin, target) == pytest.approx(expected, abs=1e-6)


def test_distance_of_a_point_to_itself_is_zero():
    assert distance_m((-72.5, 7.8), (-72.5, 7.8)) == 0
