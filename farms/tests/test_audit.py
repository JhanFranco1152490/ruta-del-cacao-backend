from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from farms.models import Farm, FarmAuditEvent
from farms.services.audit import record_farm_audit_event
from producers.models import Producer


class FarmAuditServiceTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            email="auditor@example.com",
            document_type="CC",
            identity_document="1090111111",
            password="frase segura de cacao 2026",
        )
        producer = Producer.objects.create(
            member_code="PRD-000002",
            document_type="CC",
            identity_document="1090222222",
            first_name="Productora",
            last_name="Prueba",
            municipality_code="54001",
            joined_on=date(2026, 1, 1),
        )
        self.farm = Farm.objects.create(
            producer=producer,
            name="La Esperanza",
            name_normalized="la esperanza",
            department_code="54",
            municipality_code="54001",
            area_hectares=Decimal("12.50"),
            altitude_masl=950,
            latitude=Decimal("7.8234567"),
            longitude=Decimal("-72.5123456"),
        )

    def test_records_an_audit_event_without_field_values(self):
        event = record_farm_audit_event(
            farm=self.farm,
            actor=self.actor,
            action=FarmAuditEvent.Action.UPDATED,
            changed_fields=["name", "latitude", "name"],
        )

        self.assertEqual(event.farm, self.farm)
        self.assertEqual(event.actor, self.actor)
        self.assertEqual(event.action, FarmAuditEvent.Action.UPDATED)
        self.assertEqual(event.changed_fields, ["latitude", "name"])
        self.assertIsNotNone(event.occurred_at)

    def test_rejects_unknown_actions(self):
        with self.assertRaises(ValueError):
            record_farm_audit_event(
                farm=self.farm,
                actor=self.actor,
                action="deleted",
            )
