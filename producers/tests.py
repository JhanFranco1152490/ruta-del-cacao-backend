import unittest

from producers.documents import (
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
    def test_removes_allowed_separators_and_preserves_leading_zeroes(self):
        self.assertEqual(normalize_identity_document(" 00.123-abc "), "00123ABC")

    def test_rejects_a_document_without_content(self):
        with self.assertRaises(InvalidIdentityDocument):
            normalize_identity_document(" . - ")

    def test_rejects_characters_other_than_letters_and_digits(self):
        with self.assertRaises(InvalidIdentityDocument):
            normalize_identity_document("123/456")
