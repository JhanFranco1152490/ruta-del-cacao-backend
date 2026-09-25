import unittest

from apps.producers.documents import (
    InvalidIdentityDocument,
    normalize_document_type,
    normalize_identity_document,
)


class NormalizeDocumentTypeTests(unittest.TestCase):
    def test_normalizes_an_allowed_type(self):
        self.assertEqual(normalize_document_type(" ce "), "CE")

    def test_rejects_an_unknown_type(self):
        with self.assertRaises(InvalidIdentityDocument):
            normalize_document_type("PASSPORT")


class NormalizeIdentityDocumentTests(unittest.TestCase):
    def test_accepts_digits_and_preserves_leading_zeroes(self):
        self.assertEqual(normalize_identity_document("001234"), "001234")

    def test_rejects_a_document_shorter_than_six_digits(self):
        with self.assertRaises(InvalidIdentityDocument):
            normalize_identity_document("12345")

    def test_rejects_letters_formatting_and_documents_longer_than_fifteen_digits(self):
        with self.assertRaises(InvalidIdentityDocument):
            normalize_identity_document("12.345-ABC")
        with self.assertRaises(InvalidIdentityDocument):
            normalize_identity_document("1234567890123456")
