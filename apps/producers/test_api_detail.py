from datetime import date

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.producers.models import Producer


class UserWithProducerPermissions:
    is_authenticated = True

    def has_perm(self, permission):
        return True


class ProducerAPIDetailTests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.producer = Producer.objects.create(
            member_code="PROD-000001",
            document_type="CC",
            identity_document="12345678",
            first_name="Ana",
            last_name="Gomez",
            phone="3001234567",
            email="ana@example.com",
            municipality_code="54001",
            joined_on=date.today(),
        )

    def authenticate_for_write(self):
        csrf_response = self.client.get("/api/auth/csrf")
        self.client.force_authenticate(user=UserWithProducerPermissions())
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf_response.data["csrf_token"])

    def test_returns_the_complete_producer_detail(self):
        self.client.force_authenticate(user=UserWithProducerPermissions())

        response = self.client.get(f"/api/producers/{self.producer.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "ana@example.com")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_updates_a_producer_with_the_current_version(self):
        self.authenticate_for_write()

        response = self.client.patch(
            f"/api/producers/{self.producer.id}",
            {"first_name": "Beatriz", "expected_version": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Beatriz")
        self.assertEqual(response.data["version"], 2)

    def test_deactivates_a_producer(self):
        self.authenticate_for_write()

        response = self.client.patch(
            f"/api/producers/{self.producer.id}/status",
            {"status": "inactive", "expected_version": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "inactive")
        self.assertEqual(response.data["version"], 2)

    def test_reactivates_an_inactive_producer(self):
        self.authenticate_for_write()

        self.client.patch(
            f"/api/producers/{self.producer.id}/status",
            {"status": "inactive", "expected_version": 1},
            format="json",
        )
        response = self.client.patch(
            f"/api/producers/{self.producer.id}/status",
            {"status": "active", "expected_version": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(response.data["version"], 3)

    def test_rejects_an_update_with_a_stale_version(self):
        self.authenticate_for_write()

        response = self.client.patch(
            f"/api/producers/{self.producer.id}",
            {"first_name": "Beatriz", "expected_version": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "stale_version")

    def test_returns_not_found_for_an_unknown_producer(self):
        self.client.force_authenticate(user=UserWithProducerPermissions())
        response = self.client.get("/api/producers/00000000-0000-0000-0000-000000000000")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rejects_delete(self):
        self.client.force_authenticate(user=UserWithProducerPermissions())
        response = self.client.delete(f"/api/producers/{self.producer.id}")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_rejects_an_update_with_a_duplicate_document(self):
        Producer.objects.create(
            member_code="PROD-000002",
            document_type="CC",
            identity_document="87654321",
            first_name="Beatriz",
            last_name="Lopez",
            municipality_code="54001",
            joined_on=date.today(),
        )
        self.authenticate_for_write()

        response = self.client.patch(
            f"/api/producers/{self.producer.id}",
            {"identity_document": "87654321", "expected_version": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "duplicate_document")
