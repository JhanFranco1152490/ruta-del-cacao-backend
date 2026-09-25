from rest_framework import status
from rest_framework.test import APIClient, APITestCase


class UserWithCreatePermission:
    is_authenticated = True

    def has_perm(self, permission):
        return permission == "producers.create"


class ProducerAPICSRFTests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def test_create_requires_csrf_token(self):
        self.client.force_authenticate(user=UserWithCreatePermission())

        response = self.client.post("/api/producers/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_with_csrf_token_creates_producer(self):
        csrf_response = self.client.get("/api/auth/csrf")
        csrf_token = csrf_response.data["csrf_token"]
        self.client.force_authenticate(user=UserWithCreatePermission())
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf_token)

        response = self.client.post(
            "/api/producers/",
            {
                "document_type": "CC",
                "identity_document": "12345678",
                "first_name": "Ana",
                "last_name": "Gomez",
                "phone": "3001234567",
                "email": "ana@example.com",
                "municipality_code": "54001",
                "joined_on": "2026-09-21",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertRegex(response.data["member_code"], r"^PROD-\d{6}$")
        self.assertEqual(response["Location"], f"/api/producers/{response.data['id']}")

    def test_create_rejects_a_duplicate_document(self):
        csrf_response = self.client.get("/api/auth/csrf")
        self.client.force_authenticate(user=UserWithCreatePermission())
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf_response.data["csrf_token"])
        data = {
            "document_type": "CC",
            "identity_document": "12345678",
            "first_name": "Ana",
            "last_name": "Gomez",
            "municipality_code": "54001",
            "joined_on": "2026-09-21",
        }

        self.client.post("/api/producers/", data, format="json")
        response = self.client.post("/api/producers/", data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "duplicate_document")

    def test_create_returns_a_validation_error_for_unknown_fields(self):
        csrf_response = self.client.get("/api/auth/csrf")
        self.client.force_authenticate(user=UserWithCreatePermission())
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf_response.data["csrf_token"])
        response = self.client.post("/api/producers/", {"unexpected": "value"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIn("unexpected", response.data["fields"])
