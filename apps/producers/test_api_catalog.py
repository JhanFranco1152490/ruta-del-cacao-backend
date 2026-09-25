from rest_framework import status
from rest_framework.test import APISimpleTestCase


class UserWithCatalogPermission:
    is_authenticated = True

    def has_perm(self, permission):
        return permission == "producers.create"


class MunicipalityCatalogAPITests(APISimpleTestCase):
    def test_returns_norte_de_santander_municipalities(self):
        self.client.force_authenticate(user=UserWithCatalogPermission())

        response = self.client.get("/api/catalogs/municipalities")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 40)
        self.assertEqual(response.data["results"][0]["code"], "54003")
        self.assertEqual(response.data["results"][0]["name"], "\u00c1brego")
