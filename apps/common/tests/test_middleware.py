import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.common.middleware import ApiNoStoreMiddleware

pytestmark = pytest.mark.django_db


def test_api_responses_are_never_cached(client):
    response = client.get("/api/auth/csrf")

    assert "no-store" in response["Cache-Control"]


def test_non_api_responses_are_left_alone(client):
    response = client.get("/ruta-que-no-existe")

    assert "no-store" not in response.get("Cache-Control", "")


def test_api_is_recognized_when_the_app_is_mounted_under_a_prefix():
    request = RequestFactory().get("/api/producers", SCRIPT_NAME="/backend")

    response = ApiNoStoreMiddleware(lambda _request: HttpResponse())(request)

    assert request.path == "/backend/api/producers"
    assert "no-store" in response["Cache-Control"]
