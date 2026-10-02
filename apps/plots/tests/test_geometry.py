import math
from decimal import Decimal

import pytest

from apps.plots.exceptions import InvalidBoundary
from apps.plots.geometry import (
    declared_area_matches,
    find_overlaps,
    measured_area_hectares,
    suggest_boundary,
    to_polygon,
    validate_boundary,
)

# Cerca de 7,8° de latitud, 0,001° son unos 110 m en cada eje.
LON = Decimal("-72.5")
LAT = Decimal("7.8")
STEP = Decimal("0.001")


def vertex(lon, lat, source="map", accuracy_m=None):
    return {
        "latitude": Decimal(lat),
        "longitude": Decimal(lon),
        "accuracy_m": accuracy_m,
        "captured_at": None,
        "source": source,
    }


def rect(x0, y0, x1, y1):
    """Rectángulo en pasos de STEP a partir de (LON, LAT)."""
    left, right = LON + STEP * Decimal(x0), LON + STEP * Decimal(x1)
    bottom, top = LAT + STEP * Decimal(y0), LAT + STEP * Decimal(y1)
    return [vertex(left, bottom), vertex(right, bottom), vertex(right, top), vertex(left, top)]


def polygon(vertices):
    return to_polygon(validate_boundary(vertices).vertices)


def coordinates(vertices):
    return {(v["longitude"], v["latitude"]) for v in vertices}


class TestValidateBoundary:
    def test_accepts_a_triangle_and_the_largest_polygon(self):
        validate_boundary(rect(0, 0, 1, 1)[:3])

        circle = [
            vertex(LON + STEP * Decimal(x), LAT + STEP * Decimal(y))
            for x, y in _regular_polygon(100)
        ]
        assert len(validate_boundary(circle).vertices) == 100

    @pytest.mark.parametrize("count", [0, 2])
    def test_rejects_fewer_than_three_vertices(self, count):
        with pytest.raises(InvalidBoundary) as error:
            validate_boundary(rect(0, 0, 1, 1)[:count])

        assert "al menos 3 vértices" in error.value.fields["boundary"][0]

    def test_rejects_more_than_one_hundred_vertices(self):
        circle = [
            vertex(LON + STEP * Decimal(x), LAT + STEP * Decimal(y))
            for x, y in _regular_polygon(101)
        ]

        with pytest.raises(InvalidBoundary) as error:
            validate_boundary(circle)

        assert "más de 100 vértices" in error.value.fields["boundary"][0]

    def test_rejects_sides_that_cross(self):
        bottom_left, bottom_right, top_right, top_left = rect(0, 0, 1, 1)

        with pytest.raises(InvalidBoundary) as error:
            validate_boundary([bottom_left, top_right, bottom_right, top_left])

        assert "se cruzan" in error.value.fields["boundary"][0]

    @pytest.mark.parametrize(
        ("lon", "lat"), [("-72.5", "90.0000001"), ("-180.0000001", "7.8"), ("180.1", "7.8")]
    )
    def test_rejects_coordinates_out_of_range(self, lon, lat):
        vertices = rect(0, 0, 1, 1)
        vertices[0] = vertex(lon, lat)

        with pytest.raises(InvalidBoundary) as error:
            validate_boundary(vertices)

        assert "fuera de rango" in error.value.fields["boundary"][0]

    def test_rejects_a_repeated_vertex(self):
        vertices = rect(0, 0, 1, 1)
        vertices.insert(2, dict(vertices[1]))

        with pytest.raises(InvalidBoundary) as error:
            validate_boundary(vertices)

        assert "repetidos" in error.value.fields["boundary"][0]

    def test_rejects_the_first_vertex_repeated_at_the_end(self):
        vertices = rect(0, 0, 1, 1)

        with pytest.raises(InvalidBoundary):
            validate_boundary([*vertices, dict(vertices[0])])

    def test_rejects_vertices_that_enclose_no_area(self):
        aligned = [vertex(LON, LAT), vertex(LON + STEP, LAT), vertex(LON + 2 * STEP, LAT)]

        with pytest.raises(InvalidBoundary) as error:
            validate_boundary(aligned)

        assert "no encierra" in error.value.fields["boundary"][0]

    def test_rounds_coordinates_to_seven_decimals_and_keeps_the_rest(self):
        vertices = rect(0, 0, 1, 1)
        vertices[0] = vertex("-72.50000004", "7.80000006", source="gps", accuracy_m=Decimal("4"))

        first = validate_boundary(vertices).vertices[0]

        assert first["longitude"] == Decimal("-72.5000000")
        assert first["latitude"] == Decimal("7.8000001")
        assert (first["source"], first["accuracy_m"]) == ("gps", Decimal("4"))

    def test_treats_coordinates_written_differently_as_the_same(self):
        written = [{**v, "latitude": Decimal(f"{v['latitude']}000")} for v in rect(0, 0, 1, 1)]

        assert validate_boundary(written).vertices == validate_boundary(rect(0, 0, 1, 1)).vertices


class TestAreas:
    def test_measured_area_has_four_decimals(self):
        area = measured_area_hectares(polygon(rect(0, 0, 1, 1)))

        assert area == area.quantize(Decimal("0.0001"))
        assert Decimal("1.2") < area < Decimal("1.3")

    @pytest.mark.parametrize(
        ("declared", "matches"),
        [("2.41", True), ("2.29", True), ("2.53", True), ("2.28", False), ("2.54", False)],
    )
    def test_declared_area_may_differ_up_to_five_percent(self, declared, matches):
        # El 5 % de 2,41 es 0,1205: el rango aceptado va de 2,2895 a 2,5305.
        assert declared_area_matches(Decimal(declared), Decimal("2.4100")) is matches

    def test_exactly_five_percent_is_accepted(self):
        assert declared_area_matches(Decimal("1.05"), Decimal("1.0000")) is True
        assert declared_area_matches(Decimal("0.95"), Decimal("1.0000")) is True


class TestOverlaps:
    def test_plots_sharing_a_side_do_not_overlap(self):
        assert find_overlaps(polygon(rect(0, 0, 1, 1)), {"P2": polygon(rect(1, 0, 2, 1))}) == []

    def test_an_overlap_under_one_square_metre_counts_as_a_shared_side(self):
        # Una franja de 0,0000001° (1 cm) de ancho a lo largo de un lado de 11 m: 0,1 m².
        own = polygon(
            [vertex(LON, LAT), vertex("-72.4999", LAT), vertex("-72.4999", "7.8001"),
             vertex(LON, "7.8001")]  # fmt: skip
        )
        neighbour = polygon(
            [vertex("-72.4999001", LAT), vertex("-72.4998", LAT), vertex("-72.4998", "7.8001"),
             vertex("-72.4999001", "7.8001")]  # fmt: skip
        )

        assert find_overlaps(own, {"P2": neighbour}) == []

    def test_reports_each_neighbour_overlapped_with_its_area(self):
        own = polygon(rect(0, 0, 2, 2))

        overlaps = find_overlaps(
            own,
            {
                "P2": polygon(rect(1, 0, 3, 2)),
                "P3": polygon(rect(0, 3, 1, 4)),
                "P4": polygon(rect(-1, -1, 1, 1)),
            },
        )

        assert [overlap.key for overlap in overlaps] == ["P2", "P4"]
        p2, p4 = overlaps
        # P2 cubre la mitad de la parcela; P4, un cuarto.
        assert p2.area_hectares == measured_area_hectares(polygon(rect(1, 0, 2, 2)))
        assert p4.area_hectares == measured_area_hectares(polygon(rect(0, 0, 1, 1)))


class TestSuggestBoundary:
    def test_moves_the_invading_vertices_to_the_neighbour_border(self):
        own = validate_boundary(rect(0, 0, 2, 1))
        own.vertices[0]["source"] = "gps"
        neighbour = polygon(rect(1, 0, 3, 1))

        suggestion = suggest_boundary(own, [neighbour])

        assert coordinates(suggestion) == coordinates(rect(0, 0, 1, 1))
        sources = {(v["longitude"], v["latitude"]): v["source"] for v in suggestion}
        assert sources[(LON, LAT)] == "gps"
        assert sources[(LON + STEP, LAT)] == "adjusted"
        assert sources[(LON + STEP, LAT + STEP)] == "adjusted"

    def test_adds_the_points_where_the_borders_cross(self):
        own = validate_boundary(rect(0, 0, 2, 2))
        neighbour = polygon(rect(1, 1, 3, 3))

        suggestion = suggest_boundary(own, [neighbour])

        # Una L: se pierde la esquina invadida y aparecen los dos cruces y la esquina vecina.
        assert len(suggestion) == 6
        assert coordinates(suggestion) >= {
            (LON + 2 * STEP, LAT + STEP),
            (LON + STEP, LAT + 2 * STEP),
            (LON + STEP, LAT + STEP),
        }
        validate_boundary(suggestion)

    def test_keeps_away_from_every_neighbour(self):
        own = validate_boundary(rect(0, 0, 3, 1))

        suggestion = suggest_boundary(own, [polygon(rect(-1, 0, 1, 1)), polygon(rect(2, 0, 4, 1))])

        assert coordinates(suggestion) == coordinates(rect(1, 0, 2, 1))

    def test_no_suggestion_when_the_plot_is_inside_a_neighbour(self):
        own = validate_boundary(rect(1, 1, 2, 2))

        assert suggest_boundary(own, [polygon(rect(0, 0, 3, 3))]) is None

    def test_no_suggestion_when_cutting_splits_the_plot(self):
        own = validate_boundary(rect(0, 0, 3, 1))

        assert suggest_boundary(own, [polygon(rect(1, -1, 2, 2))]) is None

    def test_no_suggestion_when_cutting_leaves_a_hole(self):
        own = validate_boundary(rect(0, 0, 3, 3))

        assert suggest_boundary(own, [polygon(rect(1, 1, 2, 2))]) is None

    def test_ignores_slivers_under_one_square_metre(self):
        # La vecina deja fuera una franja de 1 cm por 5 m: no es una parcela que sugerir.
        own = validate_boundary(rect(0, 0, 2, "0.05"))
        neighbour = polygon(
            [vertex("-72.4999999", LAT), vertex("-72.498", LAT), vertex("-72.498", "7.801"),
             vertex("-72.4999999", "7.801")]  # fmt: skip
        )

        assert suggest_boundary(own, [neighbour]) is None


def _regular_polygon(sides):
    return [
        (
            round(Decimal(math.cos(2 * math.pi * i / sides)), 7),
            round(Decimal(math.sin(2 * math.pi * i / sides)), 7),
        )
        for i in range(sides)
    ]
