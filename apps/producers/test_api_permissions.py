from rest_framework import status
from rest_framework.test import APISimpleTestCase


class UserWithoutProducerPermission:
    is_authenticated = True

    def has_perm(self, permission):
        return False


class ProducerAPIPermissionTests(APISimpleTestCase):
    def test_list_requires_view_permission(self):
        self.client.force_authenticate(user=UserWithoutProducerPermission())

        response = self.client.get("/api/producers/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
