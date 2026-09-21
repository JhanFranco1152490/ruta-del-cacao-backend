from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from producers.models import Producer


class UserWithViewPermission:
    is_authenticated = True

    def has_perm(self, permission):
        return permission == "producers.view"


class ProducerAPIListTests(APITestCase):
    def test_authorized_user_receives_a_paginated_list(self):
        Producer.objects.create(member_code="PROD-000001", document_type="CC", identity_document="1", first_name="Ana", last_name="Perez", municipality_code="54001", joined_on=date.today())
        self.client.force_authenticate(user=UserWithViewPermission())

        response = self.client.get("/api/producers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["member_code"], "PROD-000001")
