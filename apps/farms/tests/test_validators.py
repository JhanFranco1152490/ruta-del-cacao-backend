from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.farms.models import Farm
from apps.farms.validators import validate_altitude


class FarmValidatorTests(SimpleTestCase):
    def test_altitude_validator_rejects_values_out_of_range(self):
        for value in (-501, 9001):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_altitude(value)

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
