import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.tests.helpers import open_session


@pytest.fixture(autouse=True)
def _clear_cache():
    # Los límites de solicitudes viven en la caché; sin esto un test hereda los intentos
    # del anterior.
    cache.clear()


@pytest.fixture
def anonymous_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def api_client(anonymous_client):
    """Cliente que se comporta como el navegador: exige CSRF y ya trae el token."""
    csrf_token = anonymous_client.get("/api/auth/csrf").data["csrf_token"]
    anonymous_client.credentials(HTTP_X_CSRFTOKEN=csrf_token)
    return anonymous_client


@pytest.fixture
def auth_client(api_client):
    """Devuelve una función que abre una sesión real (cookies JWT) para el usuario dado."""

    def _login(user):
        return open_session(api_client, user)

    return _login
