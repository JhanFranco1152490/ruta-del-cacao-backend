import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_any_authenticated_user_can_read_the_catalog():
    client = APIClient()
    client.force_authenticate(
        User.objects.create_user(
            email="catalogo@example.com", document_type="CC", identity_document="100"
        )
    )

    response = client.get("/api/catalogs/municipalities")

    assert response.status_code == 200
    assert len(response.data["results"]) == 40
    assert response.data["results"][0] == {"code": "54003", "name": "Ábrego"}


def test_catalog_requires_authentication():
    response = APIClient().get("/api/catalogs/municipalities")

    assert response.status_code == 401
