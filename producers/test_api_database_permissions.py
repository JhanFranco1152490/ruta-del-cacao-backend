from django.contrib.auth.models import Permission
from rest_framework import status
from rest_framework.test import APITestCase

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
