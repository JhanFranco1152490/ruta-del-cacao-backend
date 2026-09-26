from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from farms.models import Farm
from farms.validators import (
    normalize_farm_name,
    validate_altitude,
    validate_latitude,
    validate_longitude,
    validate_positive_area,
)


class FarmValidatorTests(SimpleTestCase):
    def test_name_normalization_trims_and_ignores_case(self):
        self.assertEqual(normalize_farm_name("  La Esperanza  "), "la esperanza")

    def test_numeric_domain_validators_reject_invalid_values(self):
        invalid_values = (
            (validate_positive_area, Decimal("0")),
            (validate_altitude, -501),
            (validate_altitude, 9001),
            (validate_latitude, Decimal("90.0000001")),
            (validate_longitude, Decimal("-180.0000001")),
        )

        for validator, value in invalid_values:
            with self.subTest(validator=validator.__name__, value=value):
                with self.assertRaises(ValidationError):
                    validator(value)

    def test_model_normalizes_name_and_accepts_a_valid_territory(self):
        farm = Farm(
            name="  La Esperanza  ",
            department_code=" 54 ",
            municipality_code=" 54001 ",
        )

        farm.clean()

        self.assertEqual(farm.name, "La Esperanza")
        self.assertEqual(farm.name_normalized, "la esperanza")
        self.assertEqual(farm.department_code, "54")
        self.assertEqual(farm.municipality_code, "54001")

    def test_model_rejects_unknown_territorial_codes(self):
        farm = Farm(name="La Esperanza", department_code="99", municipality_code="99999")

        with self.assertRaises(ValidationError) as error:
            farm.clean()

        self.assertIn("department_code", error.exception.message_dict)
        self.assertIn("municipality_code", error.exception.message_dict)
