import unittest

from apps.producers.contacts import InvalidPhoneNumber, normalize_phone


class NormalizePhoneTests(unittest.TestCase):
    def test_returns_none_for_an_omitted_or_empty_value(self):
        self.assertIsNone(normalize_phone(None))
        self.assertIsNone(normalize_phone("   "))

    def test_accepts_a_phone_number_with_ten_digits(self):
        self.assertEqual(normalize_phone("3001234567"), "3001234567")

    def test_rejects_formatting_characters(self):
        with self.assertRaises(InvalidPhoneNumber):
            normalize_phone("300 123 4567")

    def test_rejects_too_few_digits(self):
        with self.assertRaises(InvalidPhoneNumber):
            normalize_phone("123456")

    def test_rejects_more_than_ten_digits(self):
        with self.assertRaises(InvalidPhoneNumber):
            normalize_phone("12345678901")
