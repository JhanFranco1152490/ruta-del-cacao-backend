from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.db.models import PROTECT, ProtectedError
from django.test import TestCase

from apps.farms.models import Farm
from apps.producers.models import Producer


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

    def test_a_producer_with_farms_cannot_be_deleted(self):
        farm = self.create_farm()

        with self.assertRaises(ProtectedError):
            self.producer.delete()

        self.assertTrue(Producer.objects.filter(pk=self.producer.pk).exists())
        self.assertTrue(Farm.objects.filter(pk=farm.pk).exists())

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

    def test_farms_can_be_viewed_added_and_changed_but_never_deleted(self):
        codenames = set(
            Permission.objects.filter(content_type__app_label="farms").values_list(
                "codename", flat=True
            )
        )

        self.assertTrue({"view_farm", "add_farm", "change_farm"} <= codenames)
        self.assertNotIn("delete_farm", codenames)

    def test_farm_permissions_are_named_in_spanish_for_the_role_editor(self):
        names = dict(
            Permission.objects.filter(
                content_type__app_label="farms", content_type__model="farm"
            ).values_list("codename", "name")
        )

        self.assertEqual(
            names,
            {
                "view_farm": "Puede consultar fincas",
                "add_farm": "Puede registrar fincas",
                "change_farm": "Puede editar, activar y desactivar fincas",
            },
        )
