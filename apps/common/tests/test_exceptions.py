import pytest
from django.core.exceptions import NON_FIELD_ERRORS, RequestDataTooBig, SuspiciousOperation
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.test import override_settings
from rest_framework import exceptions, status
from rest_framework_simplejwt.exceptions import InvalidToken

from apps.common.exceptions import (
    AUTHENTICATION_FAILED_DETAIL,
    INTERNAL_ERROR_DETAIL,
    PARSE_ERROR_DETAIL,
    ApiError,
    PayloadTooLarge,
    api_exception_handler,
)


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


TECHNICAL_MESSAGE = "detalle técnico con datos"


def fail_deep_inside_a_service():
    raise RuntimeError(TECHNICAL_MESSAGE)


def caught(function):
    try:
        function()
    except Exception as error:
        return error


@override_settings(DEBUG=False)
def test_unhandled_error_returns_internal_error_without_details():
    response = handle(caught(fail_deep_inside_a_service))

    assert response.status_code == 500
    assert response.data["code"] == "internal_error"
    assert "detalle técnico" not in response.data["detail"]


@override_settings(DEBUG=False)
def test_unhandled_error_log_has_class_and_frames_but_never_the_message(caplog):
    handle(caught(fail_deep_inside_a_service))

    assert "RuntimeError" in caplog.text
    assert "fail_deep_inside_a_service" in caplog.text
    assert "test_exceptions.py" in caplog.text
    assert TECHNICAL_MESSAGE not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@override_settings(DEBUG=True)
def test_unhandled_error_is_reraised_in_debug():
    assert handle(RuntimeError("boom")) is None


def test_request_data_too_big_is_a_413_with_the_uniform_error():
    response = handle(RequestDataTooBig("El cuerpo supera el límite."))

    assert response.status_code == 413
    assert response.data == {
        "detail": PayloadTooLarge.default_detail,
        "code": "payload_too_large",
        "fields": {},
    }


def test_any_other_suspicious_operation_is_a_parse_error():
    response = handle(SuspiciousOperation("Host no permitido: ejemplo.invalid"))

    assert response.status_code == 400
    assert response.data["code"] == "parse_error"
    assert "ejemplo.invalid" not in response.data["detail"]
    assert response.data["fields"] == {}


@pytest.mark.parametrize("exception_class", [DjangoValidationError, exceptions.ValidationError])
def test_model_wide_error_is_the_detail_and_not_a_field(exception_class):
    response = handle(exception_class({NON_FIELD_ERRORS: ["Las fechas no coinciden."]}))

    assert response.status_code == 400
    assert response.data["detail"] == "Las fechas no coinciden."
    assert response.data["fields"] == {}


def test_extra_keys_never_replace_the_standard_ones():
    extra = {"detail": "otro", "code": "otro", "fields": {"name": ["x"]}, "existing_id": "abc"}

    response = handle(Conflict(extra=extra))

    assert response.data == {
        "detail": "Conflicto de prueba.",
        "code": "test_conflict",
        "fields": {},
        "existing_id": "abc",
    }


class ServiceUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.parametrize("exception_class", [exceptions.APIException, ServiceUnavailable])
def test_server_side_api_exception_hides_its_message(exception_class, caplog):
    def fail_with_an_api_exception():
        raise exception_class(TECHNICAL_MESSAGE)

    response = handle(caught(fail_with_an_api_exception))

    assert response.status_code == exception_class.status_code
    assert response.data == {
        "detail": INTERNAL_ERROR_DETAIL,
        "code": "internal_error",
        "fields": {},
    }
    assert exception_class.__name__ in caplog.text
    assert TECHNICAL_MESSAGE not in caplog.text


@pytest.mark.parametrize(
    ("exc", "code", "detail"),
    [
        (
            exceptions.ParseError("JSON parse error - Expecting value: line 1 column 2 (char 1)"),
            "parse_error",
            PARSE_ERROR_DETAIL,
        ),
        (InvalidToken(), "authentication_failed", AUTHENTICATION_FAILED_DETAIL),
        (
            exceptions.AuthenticationFailed("User not found"),
            "authentication_failed",
            AUTHENTICATION_FAILED_DETAIL,
        ),
    ],
)
def test_parse_and_authentication_errors_have_a_fixed_detail(exc, code, detail):
    response = handle(exc)

    assert response.data["code"] == code
    assert response.data["detail"] == detail
