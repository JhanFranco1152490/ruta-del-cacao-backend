import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.test import override_settings
from rest_framework import exceptions, status

from apps.common.exceptions import ApiError, api_exception_handler


class Conflict(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Conflicto de prueba."
    default_code = "test_conflict"


def handle(exc):
    return api_exception_handler(exc, {"view": None})


def test_field_errors_become_validation_error_with_fields():
    response = handle(exceptions.ValidationError({"email": ["Correo inválido."]}))

    assert response.status_code == 400
    assert response.data == {
        "detail": "Los datos enviados no son válidos.",
        "code": "validation_error",
        "fields": {"email": ["Correo inválido."]},
    }


def test_non_field_error_becomes_the_detail():
    response = handle(exceptions.ValidationError({"non_field_errors": ["Falta un campo."]}))

    assert response.data["detail"] == "Falta un campo."
    assert response.data["fields"] == {}


def test_list_validation_error_uses_first_message():
    response = handle(exceptions.ValidationError(["Primero.", "Segundo."]))

    assert response.data["detail"] == "Primero."
    assert response.data["code"] == "validation_error"


def test_nested_field_errors_are_flattened():
    response = handle(exceptions.ValidationError({"address": {"city": ["Requerido."]}}))

    assert response.data["fields"] == {"address": ["Requerido."]}


def test_django_validation_error_is_a_validation_error():
    response = handle(DjangoValidationError({"joined_on": ["La fecha no puede ser futura."]}))

    assert response.status_code == 400
    assert response.data["fields"] == {"joined_on": ["La fecha no puede ser futura."]}


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code"),
    [
        (exceptions.NotAuthenticated(), 401, "not_authenticated"),
        (exceptions.AuthenticationFailed(), 401, "authentication_failed"),
        (exceptions.PermissionDenied(), 403, "permission_denied"),
        (DjangoPermissionDenied(), 403, "permission_denied"),
        (exceptions.NotFound(), 404, "not_found"),
        (Http404(), 404, "not_found"),
        (exceptions.MethodNotAllowed("DELETE"), 405, "method_not_allowed"),
        (exceptions.Throttled(wait=30), 429, "throttled"),
    ],
)
def test_standard_errors_have_stable_codes(exc, expected_status, expected_code):
    response = handle(exc)

    assert response.status_code == expected_status
    assert response.data["code"] == expected_code
    assert isinstance(response.data["detail"], str)
    assert response.data["fields"] == {}


def test_throttled_keeps_retry_after_header():
    response = handle(exceptions.Throttled(wait=30))

    assert response["Retry-After"] == "30"


def test_custom_error_carries_code_fields_and_extra_keys():
    response = handle(Conflict(fields={"name": ["Repetido."]}, extra={"existing_id": "abc"}))

    assert response.status_code == 409
    assert response.data == {
        "detail": "Conflicto de prueba.",
        "code": "test_conflict",
        "fields": {"name": ["Repetido."]},
        "existing_id": "abc",
    }


@override_settings(DEBUG=False)
def test_unhandled_error_returns_internal_error_without_details(caplog):
    response = handle(RuntimeError("detalle técnico con datos"))

    assert response.status_code == 500
    assert response.data["code"] == "internal_error"
    assert "detalle técnico" not in response.data["detail"]
    assert "detalle técnico con datos" in caplog.text


@override_settings(DEBUG=True)
def test_unhandled_error_is_reraised_in_debug():
    assert handle(RuntimeError("boom")) is None
