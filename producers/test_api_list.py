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
        Producer.objects.create(
            member_code="PROD-000001",
            document_type="CC",
            identity_document="1",
            first_name="Ana",
            last_name="Perez",
            municipality_code="54001",
            joined_on=date.today(),
        )
        self.client.force_authenticate(user=UserWithViewPermission())

        response = self.client.get("/api/producers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["member_code"], "PROD-000001")

        result = response.data["results"][0]
        self.assertNotIn("phone", result)
        self.assertNotIn("email", result)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_filters_and_paginates_through_the_api(self):
        Producer.objects.create(
            member_code="PROD-000001",
            document_type="CC",
            identity_document="1",
            first_name="Ana",
            last_name="Alvarez",
            municipality_code="54001",
            joined_on=date.today(),
        )
        Producer.objects.create(
            member_code="PROD-000002",
            document_type="CC",
            identity_document="2",
            first_name="Beatriz",
            last_name="Zuluaga",
            municipality_code="54001",
            joined_on=date.today(),
        )
        Producer.objects.create(
            member_code="PROD-000003",
            document_type="CC",
            identity_document="3",
            first_name="Carlos",
            last_name="Perez",
            municipality_code="54003",
            joined_on=date.today(),
        )
        self.client.force_authenticate(user=UserWithViewPermission())
