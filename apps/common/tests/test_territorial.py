from decimal import Decimal

from django.test import SimpleTestCase

from apps.common.territorial import (
    OPERATING_AREA_BOUNDS,
    InvalidDepartmentCode,
    InvalidMunicipalityCode,
    coordinates_outside_operating_area,
    get_department,
    get_municipality,
    validate_municipality_department,
)


class TerritorialCatalogTests(SimpleTestCase):
    def test_department_uses_its_divipola_code(self):
        department = get_department("54")

        self.assertEqual(department.code, "54")
        self.assertEqual(department.name, "Norte de Santander")

    def test_existing_municipality_uses_its_divipola_code(self):
        municipality = get_municipality("54001")

        self.assertEqual(municipality.code, "54001")
        self.assertEqual(municipality.name, "Cúcuta")
        self.assertEqual(municipality.department_code, "54")

    def test_unknown_codes_are_rejected(self):
        with self.assertRaises(InvalidDepartmentCode):
            get_department("99")

        with self.assertRaises(InvalidMunicipalityCode):
            get_municipality("99999")

    def test_municipality_must_belong_to_the_selected_department(self):
        municipality = validate_municipality_department("54001", "54")

        self.assertEqual(municipality.code, "54001")


class OperatingAreaTests(SimpleTestCase):
    def test_bounds_are_the_same_numbers_the_frontend_uses(self):
        # Si cambian aquí sin cambiar en el frontend, un punto aceptado en el teléfono se
        # rechazaría al sincronizar y quedaría trabado en la cola.
        self.assertEqual(OPERATING_AREA_BOUNDS.min_latitude, Decimal("6.872"))
        self.assertEqual(OPERATING_AREA_BOUNDS.max_latitude, Decimal("9.291"))
        self.assertEqual(OPERATING_AREA_BOUNDS.min_longitude, Decimal("-73.634"))
        self.assertEqual(OPERATING_AREA_BOUNDS.max_longitude, Decimal("-72.047"))

    def test_a_point_inside_or_on_the_border_is_inside(self):
        for latitude, longitude in [
            (Decimal("7.8234567"), Decimal("-72.5123456")),
            (Decimal("6.872"), Decimal("-73.634")),
            (Decimal("9.291"), Decimal("-72.047")),
        ]:
            with self.subTest(latitude=latitude, longitude=longitude):
                self.assertEqual(coordinates_outside_operating_area(latitude, longitude), [])

    def test_reports_which_coordinate_is_outside(self):
        cases = [
            (Decimal("6.8719999"), Decimal("-72.5"), ["latitude"]),
            (Decimal("9.2910001"), Decimal("-72.5"), ["latitude"]),
            (Decimal("7.8"), Decimal("-73.6340001"), ["longitude"]),
            (Decimal("7.8"), Decimal("-72.0469999"), ["longitude"]),
            (Decimal("4.6"), Decimal("-74.08"), ["latitude", "longitude"]),
        ]
        for latitude, longitude, expected in cases:
            with self.subTest(latitude=latitude, longitude=longitude):
                self.assertEqual(coordinates_outside_operating_area(latitude, longitude), expected)
