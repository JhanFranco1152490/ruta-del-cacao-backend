from django.contrib.auth.models import Permission
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from accounts.models import User


class ProducerAPIDatabasePermissionTests(APITestCase):
    def test_user_with_the_stored_view_permission_can_list_producers(self):
        user = User.objects.create_user(
            email="admin@example.com",
            document_type="CC",
            identity_document="100",
            password="safe-password",
        )
        permission = Permission.objects.get(content_type__app_label="producers", codename="view")
        user.user_permissions.add(permission)
        self.client.force_authenticate(user=user)
        response = self.client.get("/api/producers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_with_the_stored_create_permission_can_create_a_producer(self):
        user = User.objects.create_user(
            email="creator@example.com",
            document_type="CC",
            identity_document="200",
            password="safe-password",
        )
        permission = Permission.objects.get(content_type__app_label="producers", codename="create")
        user.user_permissions.add(permission)
        client = APIClient(enforce_csrf_checks=True)
        csrf_response = client.get("/api/auth/csrf")
        client.force_authenticate(user=user)
        client.credentials(HTTP_X_CSRFTOKEN=csrf_response.data["csrf_token"])

        response = client.post(
            "/api/producers/",
            {
                "document_type": "CC",
                "identity_document": "12345678",
                "first_name": "Ana",
                "last_name": "Gomez",
                "municipality_code": "54001",
                "joined_on": "2026-09-21",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
