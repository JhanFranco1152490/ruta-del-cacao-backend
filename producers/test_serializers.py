from datetime import date

from django.test import SimpleTestCase

from producers.serializers import (
    ProducerCreateSerializer,
    ProducerListQuerySerializer,
    ProducerStatusSerializer,
    ProducerUpdateSerializer,
)


class ProducerCreateSerializerTests(SimpleTestCase):
    def valid_data(self):
        return {
            "document_type": "CC",
            "identity_document": "00.123-abc",
            "first_name": "Ana",
            "last_name": "P?rez",
            "municipality_code": "54001",
            "joined_on": str(date.today()),
        }

    def test_normalizes_document_and_optional_contact(self):
        serializer = ProducerCreateSerializer(data={**self.valid_data(), "phone": "3001234567"})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["identity_document"], "00123ABC")

    def test_rejects_a_phone_with_formatting_characters(self):
        serializer = ProducerCreateSerializer(data={**self.valid_data(), "phone": "300 123 4567"})

        self.assertFalse(serializer.is_valid())
        self.assertIn("phone", serializer.errors)


class ProducerUpdateSerializerTests(SimpleTestCase):
    def test_requires_a_field_besides_expected_version(self):
        serializer = ProducerUpdateSerializer(data={"expected_version": 1})

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)


class ProducerStatusSerializerTests(SimpleTestCase):
    def test_rejects_reactivation(self):
        serializer = ProducerStatusSerializer(data={"status": "active", "expected_version": 1})

        self.assertFalse(serializer.is_valid())
        self.assertIn("status", serializer.errors)


class ProducerListQuerySerializerTests(SimpleTestCase):
    def test_applies_pagination_defaults(self):
        serializer = ProducerListQuerySerializer(data={})

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["page"], 1)
        self.assertEqual(serializer.validated_data["page_size"], 20)

    def test_rejects_a_page_size_above_the_limit(self):
        serializer = ProducerListQuerySerializer(data={"page_size": 101})

        self.assertFalse(serializer.is_valid())
        self.assertIn("page_size", serializer.errors)
