import json

import pytest
from django.test import RequestFactory
from django.urls import get_resolver
from rest_framework.exceptions import NotFound

from apps.common.exceptions import INTERNAL_ERROR_DETAIL, api_exception_handler
from apps.common.views import not_found, server_error


def not_found_body():
    """Lo que responde la API cuando un recurso no existe: la ruta desconocida debe igualarlo."""
    return api_exception_handler(NotFound(), {"view": None}).data


@pytest.mark.parametrize("path", ["/api/nope", "/api/producers/abc", "/api"])
def test_unresolved_api_route_returns_the_uniform_not_found(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == not_found_body()
    assert response.json()["code"] == "not_found"
    assert "no-store" in response["Cache-Control"]


def test_unresolved_route_outside_the_api_keeps_the_html_page(client):
    response = client.get("/ruta-que-no-existe")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("text/html")


def test_not_found_view_answers_json_only_under_the_api():
    factory = RequestFactory()

    api_response = not_found(factory.get("/api/nope"))
    page_response = not_found(factory.get("/ruta-que-no-existe"))

    assert api_response["Content-Type"].startswith("application/json")
    assert page_response["Content-Type"].startswith("text/html")


def test_server_error_under_the_api_returns_the_uniform_internal_error():
    response = server_error(RequestFactory().get("/api/producers"))

    assert response.status_code == 500
    assert response["Content-Type"].startswith("application/json")
    assert json.loads(response.content) == {
        "detail": INTERNAL_ERROR_DETAIL,
        "code": "internal_error",
        "fields": {},
    }


def test_server_error_outside_the_api_keeps_the_html_page():
    response = server_error(RequestFactory().get("/admin/"))

    assert response.status_code == 500
    assert response["Content-Type"].startswith("text/html")


TECHNICAL_MESSAGE = "detalle técnico con datos"


def fail_inside_a_middleware():
    raise RuntimeError(TECHNICAL_MESSAGE)


@pytest.mark.parametrize("path", ["/api/producers", "/admin/"])
def test_server_error_logs_class_and_frames_but_never_the_message(caplog, path):
    # Django llama a la vista de error 500 mientras atiende la excepción.
    try:
        fail_inside_a_middleware()
    except RuntimeError:
        server_error(RequestFactory().get(path))

    assert "RuntimeError" in caplog.text
    assert "fail_inside_a_middleware" in caplog.text
    assert TECHNICAL_MESSAGE not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_error_handlers_are_registered_in_the_root_urlconf():
    resolver = get_resolver()

    assert resolver.resolve_error_handler(404) is not_found
    assert resolver.resolve_error_handler(500) is server_error
