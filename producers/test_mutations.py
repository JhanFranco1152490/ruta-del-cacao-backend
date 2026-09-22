from datetime import date

from django.test import TestCase

from producers.models import Producer
from producers.status import deactivate_producer
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

    def test_deactivates_once_with_the_current_version(self):
        producer = deactivate_producer(self.producer.id, 1)
        repeated = deactivate_producer(producer.id, 2)

        self.assertEqual(producer.status, "inactive")
        self.assertEqual(producer.version, 2)
        self.assertEqual(repeated.version, 2)
