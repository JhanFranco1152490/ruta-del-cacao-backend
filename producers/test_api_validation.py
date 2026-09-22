from rest_framework import status
from rest_framework.test import APITestCase


class UserWithCreatePermission:
    is_authenticated = True

    def has_perm(self, permission):
        return permission == "producers.create"


class ProducerAPIValidationTests(APITestCase):
    def authenticate_for_write(self):
        csrf_response = self.client.get("/api/auth/csrf")
        self.client.force_authenticate(user=UserWithCreatePermission())
        self.client.credentials(HTTP_X_CSRFTOKEN=csrf_response.data["csrf_token"])

    def producer_data(self):
        return {
            "document_type": "CC",
            "identity_document": "12345678",
            "first_name": "Ana",
            "last_name": "Gomez",
            "municipality_code": "54001",
            "joined_on": "2026-09-21",
        }

    def post_producer(self, data):
        self.authenticate_for_write()
        return self.client.post("/api/producers/", data, format="json")

    def test_create_rejects_an_invalid_email_as_a_validation_error(self):
        response = self.post_producer({**self.producer_data(), "email": "invalid-email"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIn("email", response.data["fields"])

    def test_create_rejects_a_future_joined_on_as_a_validation_error(self):
        response = self.post_producer({**self.producer_data(), "joined_on": "2999-01-01"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIn("joined_on", response.data["fields"])

    def test_create_accepts_a_null_email(self):
        response = self.post_producer({**self.producer_data(), "email": None})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["email"])
