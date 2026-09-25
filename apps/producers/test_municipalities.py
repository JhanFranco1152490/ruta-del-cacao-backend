import unittest

from apps.producers.municipalities import InvalidMunicipalityCode, validate_municipality_code


class MunicipalityCodeTests(unittest.TestCase):
    def test_accepts_a_norte_de_santander_code(self):
        self.assertEqual(validate_municipality_code("54001"), "54001")

    def test_rejects_a_code_from_another_department(self):
        with self.assertRaises(InvalidMunicipalityCode):
            validate_municipality_code("11001")
