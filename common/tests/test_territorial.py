from django.test import SimpleTestCase

from common.territorial import (
    InvalidDepartmentCode,
    InvalidMunicipalityCode,
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
