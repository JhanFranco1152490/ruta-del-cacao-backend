from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.producers.models import Producer


class ProducerValidationTests(SimpleTestCase):
    def build_producer(self, **overrides):
        values = {
            "member_code": "PROD-000001",
            "document_type": "CC",
            "identity_document": "001234",
            "first_name": " Ana ",
            "last_name": " Pérez ",
            "municipality_code": "54001",
            "joined_on": date.today(),
        }
        values.update(overrides)
        return Producer(**values)

    def validate(self, producer):
        producer.full_clean(validate_unique=False, validate_constraints=False)

    def test_strips_required_text_fields(self):
        producer = self.build_producer()

        self.validate(producer)

        self.assertEqual(producer.first_name, "Ana")
        self.assertEqual(producer.last_name, "Pérez")
        self.assertEqual(producer.municipality_code, "54001")

    def test_exposes_utf8_document_labels_and_string_representation(self):
        producer = self.build_producer(first_name="Ana", last_name="Pérez")

        self.assertEqual(Producer.DocumentType.CC.label, "Cédula de ciudadanía")
        self.assertEqual(str(producer), "PROD-000001 — Ana Pérez")

    def test_rejects_blank_required_text(self):
        producer = self.build_producer(first_name="   ")

        with self.assertRaises(ValidationError) as context:
            self.validate(producer)

        self.assertIn("first_name", context.exception.message_dict)

    def test_normalizes_an_empty_email_to_none(self):
        producer = self.build_producer(email=" ")

        self.validate(producer)

        self.assertIsNone(producer.email)

    def test_normalizes_email_to_lowercase(self):
        producer = self.build_producer(email=" ANA@EXAMPLE.COM ")

        self.validate(producer)

        self.assertEqual(producer.email, "ana@example.com")

    def test_rejects_an_invalid_email(self):
        producer = self.build_producer(email="invalid-email")

        with self.assertRaises(ValidationError) as context:
            self.validate(producer)

        self.assertIn("email", context.exception.message_dict)

    def test_rejects_a_future_join_date(self):
        producer = self.build_producer(joined_on=date.today() + timedelta(days=1))

        with self.assertRaises(ValidationError) as context:
            self.validate(producer)

        self.assertIn("joined_on", context.exception.message_dict)
