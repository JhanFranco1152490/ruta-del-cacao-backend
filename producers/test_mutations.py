from datetime import date

from django.test import TestCase

from producers.models import Producer
from producers.status import activate_producer, deactivate_producer
from producers.updates import StaleVersionError, update_producer


class ProducerMutationTests(TestCase):
    def setUp(self):
        self.producer = Producer.objects.create(
            member_code="PROD-000001",
            document_type="CC",
            identity_document="100000",
            first_name="Ana",
            last_name="Perez",
            municipality_code="54001",
            joined_on=date.today(),
        )

    def test_updates_and_increments_version(self):
        producer = update_producer(self.producer.id, 1, {"first_name": "Bea"})

        self.assertEqual(producer.first_name, "Bea")
        self.assertEqual(producer.version, 2)
        self.assertEqual(producer.member_code, "PROD-000001")

    def test_rejects_a_stale_update(self):
        with self.assertRaises(StaleVersionError):
            update_producer(self.producer.id, 2, {"first_name": "Bea"})

    def test_changes_status_once_with_the_current_version(self):
        inactive = deactivate_producer(self.producer.id, 1)
        repeated_inactive = deactivate_producer(inactive.id, 2)
        active = activate_producer(inactive.id, 2)
        repeated_active = activate_producer(active.id, 3)

        self.assertEqual(inactive.status, "inactive")
        self.assertEqual(inactive.version, 2)
        self.assertEqual(repeated_inactive.version, 2)
        self.assertEqual(active.status, "active")
        self.assertEqual(active.version, 3)
        self.assertEqual(repeated_active.version, 3)
