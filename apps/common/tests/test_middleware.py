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


def _respond(path, cache_control=None):
    def view(_request):
        response = HttpResponse()
        if cache_control:
            response["Cache-Control"] = cache_control
        return response

    return ApiNoStoreMiddleware(view)(RequestFactory().get(path))


def test_a_public_response_keeps_the_cache_its_view_chose():
    response = _respond("/api/public/lots/abc", "public, max-age=300")

    assert response["Cache-Control"] == "public, max-age=300"


def test_a_public_response_without_its_own_cache_is_not_stored():
    assert "no-store" in _respond("/api/public/lots/abc")["Cache-Control"]


def test_the_rest_of_the_api_is_never_cached_even_if_a_view_asks():
    response = _respond("/api/lots", "public, max-age=300")

    assert "no-store" in response["Cache-Control"]
    assert "public" not in response["Cache-Control"]
