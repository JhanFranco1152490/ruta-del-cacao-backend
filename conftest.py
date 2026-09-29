import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.tests.helpers import csrf_client, open_session


@pytest.fixture(autouse=True)
def _clear_cache():
    # Los límites de solicitudes viven en la caché; sin esto un test hereda los intentos
    # del anterior.
    cache.clear()


@pytest.fixture
def anonymous_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def api_client():
    return csrf_client()


@pytest.fixture
def auth_client(api_client):
    """Devuelve una función que abre una sesión real (cookies JWT) para el usuario dado."""

    def _login(user):
        return open_session(api_client, user)

    return _login


@pytest.fixture
def plain_static_files(settings):
    # Las páginas del admin piden estáticos con manifiesto, que no existen en las pruebas.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
