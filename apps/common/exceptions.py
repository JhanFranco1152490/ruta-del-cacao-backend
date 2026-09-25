import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

VALIDATION_DETAIL = "Los datos enviados no son válidos."
INTERNAL_ERROR_DETAIL = "Ocurrió un error interno. Inténtalo de nuevo más tarde."

# El frontend decide qué hacer según `code`, así que el código de los errores estándar se
# fija por clase y no se toma de exc.get_codes(), que varía según quién lanza la excepción.
STANDARD_CODES = (
    (exceptions.NotAuthenticated, "not_authenticated"),
    (exceptions.AuthenticationFailed, "authentication_failed"),
    (exceptions.PermissionDenied, "permission_denied"),
    (exceptions.NotFound, "not_found"),
    (exceptions.MethodNotAllowed, "method_not_allowed"),
    (exceptions.Throttled, "throttled"),
)


class ApiError(exceptions.APIException):
    """Error propio de la API con código estable; cada caso concreto es una subclase."""

    def __init__(self, detail=None, *, fields=None, extra=None):
        super().__init__(detail)
        self.fields = fields or {}
        self.extra = extra or {}


def api_exception_handler(exc, context):
    exc = _as_drf_exception(exc)
    response = drf_exception_handler(exc, context)
    if response is None:
        if settings.DEBUG:
            return None
        logger.error("Error no controlado en la API", exc_info=exc)
        return Response(
            _body(INTERNAL_ERROR_DETAIL, "internal_error"),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        fields, general = _split_field_errors(response.data)
        response.data = _body(general or VALIDATION_DETAIL, "validation_error", fields)
    elif isinstance(exc, ApiError):
        response.data = _body(
            _first_message(response.data), exc.default_code, exc.fields, exc.extra
        )
    else:
        response.data = _body(_first_message(response.data), _standard_code(exc))
    return response


def _as_drf_exception(exc):
    if isinstance(exc, Http404):
        return exceptions.NotFound()
    if isinstance(exc, DjangoPermissionDenied):
        return exceptions.PermissionDenied()
    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        return exceptions.ValidationError(detail)
    return exc


def _standard_code(exc):
    for exception_class, code in STANDARD_CODES:
        if isinstance(exc, exception_class):
            return code
    return getattr(exc, "default_code", "error")


def _body(detail, code, fields=None, extra=None):
    return {"detail": detail, "code": code, "fields": fields or {}, **(extra or {})}


def _split_field_errors(data):
    if not isinstance(data, dict):
        return {}, _first_message(data)
    non_field_key = api_settings.NON_FIELD_ERRORS_KEY
    fields = {name: _messages(value) for name, value in data.items() if name != non_field_key}
    general = data.get(non_field_key)
    return fields, (_first_message(general) if general else None)


def _messages(value):
    if isinstance(value, dict):
        return [message for nested in value.values() for message in _messages(nested)]
    if isinstance(value, (list, tuple)):
        return [message for item in value for message in _messages(item)]
    return [str(value)]


def _first_message(value):
    messages = _messages(value)
    return messages[0] if messages else VALIDATION_DETAIL
