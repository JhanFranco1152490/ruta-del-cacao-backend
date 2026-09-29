from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import PROTECT
from django.test import TestCase

from apps.producers.models import Producer
from farms.models import Farm


class FarmModelTests(TestCase):
    def setUp(self):
        self.producer = Producer.objects.create(
            member_code="PRD-000001",
            document_type="CC",
            identity_document="1090123456",
            first_name="Productora",
            last_name="Prueba",
            municipality_code="54001",
            joined_on=date(2026, 1, 1),
        )

    def create_farm(self, **overrides):
        fields = {
            "producer": self.producer,
            "name": "La Esperanza",
            "name_normalized": "la esperanza",
            "department_code": "54",
            "municipality_code": "54001",
            "area_hectares": Decimal("12.50"),
            "altitude_masl": 950,
            "latitude": Decimal("7.8234567"),
            "longitude": Decimal("-72.5123456"),
        }
        fields.update(overrides)
        return Farm.objects.create(**fields)

    def test_farm_has_the_expected_persistent_fields(self):
        fields = {field.name: field for field in Farm._meta.fields}

        self.assertEqual(fields["id"].get_internal_type(), "UUIDField")
        self.assertEqual(fields["producer"].remote_field.on_delete, PROTECT)
        self.assertEqual(fields["name_normalized"].editable, False)
        self.assertEqual(fields["area_hectares"].decimal_places, 2)
        self.assertEqual(fields["latitude"].decimal_places, 7)
        self.assertEqual(fields["longitude"].decimal_places, 7)
        self.assertEqual(fields["version"].default, 1)

    def test_name_is_unique_for_each_producer_after_normalization(self):
        self.create_farm()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_farm(name="Otra finca")

    def test_area_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_farm(area_hectares=Decimal("0"))

    def test_latitude_must_be_in_its_valid_range(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_farm(latitude=Decimal("90.0000001"))

    def test_longitude_must_be_in_its_valid_range(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_farm(longitude=Decimal("180.0000001"))
