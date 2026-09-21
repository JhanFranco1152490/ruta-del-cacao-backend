from rest_framework import status
from rest_framework.test import APISimpleTestCase


class ProducerAPIAccessTests(APISimpleTestCase):
    def test_list_requires_authentication(self):
        response = self.client.get("/api/producers/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
