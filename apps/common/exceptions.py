import logging
import traceback

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, RequestDataTooBig, SuspiciousOperation
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
# Es el texto que DRF ya traduce para un recurso inexistente; se reusa para que una ruta
# desconocida diga exactamente lo mismo.
NOT_FOUND_DETAIL = exceptions.NotFound.default_detail

NOT_FOUND_CODE = "not_found"
INTERNAL_ERROR_CODE = "internal_error"

PARSE_ERROR_DETAIL = "El cuerpo de la petición no es un JSON válido."
AUTHENTICATION_FAILED_DETAIL = "La sesión no es válida o venció. Inicia sesión de nuevo."
# DRF y simplejwt arman estos mensajes en inglés y con detalles técnicos (la posición del error
# en el JSON, el tipo de token), y el frontend muestra `detail` tal cual.
FIXED_DETAILS = (
    (exceptions.ParseError, PARSE_ERROR_DETAIL),
    (exceptions.AuthenticationFailed, AUTHENTICATION_FAILED_DETAIL),
)

# El frontend decide qué hacer según `code`, así que el código de los errores estándar se
# fija por clase y no se toma de exc.get_codes(), que varía según quién lanza la excepción.
STANDARD_CODES = (
    (exceptions.NotAuthenticated, "not_authenticated"),
    (exceptions.AuthenticationFailed, "authentication_failed"),
    (exceptions.PermissionDenied, "permission_denied"),
    (exceptions.NotFound, NOT_FOUND_CODE),
    (exceptions.MethodNotAllowed, "method_not_allowed"),
    (exceptions.Throttled, "throttled"),
)


class ApiError(exceptions.APIException):
    """Error propio de la API con código estable; cada caso concreto es una subclase."""

    def __init__(self, detail=None, *, fields=None, extra=None):
        super().__init__(detail)
        self.fields = fields or {}
        self.extra = extra or {}


class PayloadTooLarge(ApiError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "El cuerpo de la petición es demasiado grande."
    default_code = "payload_too_large"


def api_exception_handler(exc, context):
    exc = _as_drf_exception(exc)
    response = drf_exception_handler(exc, context)
    if response is None:
        if settings.DEBUG:
            return None
        log_unhandled_error(exc)
        return Response(
            error_body(INTERNAL_ERROR_DETAIL, INTERNAL_ERROR_CODE),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        fields, general = _split_field_errors(response.data)
        response.data = error_body(general or VALIDATION_DETAIL, "validation_error", fields)
    elif isinstance(exc, ApiError):
        response.data = error_body(
            _first_message(response.data), exc.default_code, exc.fields, exc.extra
        )
    elif response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        # Un APIException 5xx lanzado directamente trae el mensaje de quien lo lanzó, que puede
        # ser técnico o traer datos: es un error no controlado como cualquier otro.
        log_unhandled_error(exc)
        response.data = error_body(INTERNAL_ERROR_DETAIL, INTERNAL_ERROR_CODE)
    else:
        response.data = error_body(_standard_detail(exc, response.data), _standard_code(exc))
    return response


def log_unhandled_error(exc):
    # No se pasa exc_info: el mensaje de la excepción puede traer datos del usuario (un
    # IntegrityError con el valor duplicado, un fallo de envío con el destinatario). La clase
    # y las líneas del traceback bastan para ubicar el fallo.
    logger.error(
        "Error no controlado: %s\n%s",
        type(exc).__name__,
        "".join(traceback.format_tb(exc.__traceback__)),
    )


def _as_drf_exception(exc):
    if isinstance(exc, Http404):
        return exceptions.NotFound()
    if isinstance(exc, DjangoPermissionDenied):
        return exceptions.PermissionDenied()
    # Django las lanza al leer el cuerpo (tamaño máximo, demasiados campos, cabeceras
    # inválidas) y, dentro de una vista de DRF, nadie las atrapa: sin esto salen como 500.
    if isinstance(exc, RequestDataTooBig):
        return PayloadTooLarge()
    if isinstance(exc, SuspiciousOperation):
        return exceptions.ParseError()
    if isinstance(exc, DjangoValidationError):
        detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
        return exceptions.ValidationError(detail)
    return exc


def _standard_code(exc):
    for exception_class, code in STANDARD_CODES:
        if isinstance(exc, exception_class):
            return code
    return getattr(exc, "default_code", "error")


def _standard_detail(exc, data):
    for exception_class, detail in FIXED_DETAILS:
        if isinstance(exc, exception_class):
            return detail
    return _first_message(data)


def error_body(detail, code, fields=None, extra=None):
    # Las claves extra van primero para que ninguna pise la forma estándar del error.
    return {**(extra or {}), "detail": detail, "code": code, "fields": fields or {}}


def _split_field_errors(data):
    if not isinstance(data, dict):
        return {}, _first_message(data)
    # DRF agrupa en NON_FIELD_ERRORS_KEY lo que no es de un campo y Django (el clean() de un
    # modelo) lo hace en "__all__"; ninguna de las dos es un campo del formulario.
    non_field_keys = (api_settings.NON_FIELD_ERRORS_KEY, NON_FIELD_ERRORS)
    fields = {name: _messages(value) for name, value in data.items() if name not in non_field_keys}
    general = [message for key in non_field_keys for message in _messages(data.get(key, []))]
    return fields, (general[0] if general else None)


def _messages(value):
    if isinstance(value, dict):
        return [message for nested in value.values() for message in _messages(nested)]
    if isinstance(value, (list, tuple)):
        return [message for item in value for message in _messages(item)]
    return [str(value)]


def _first_message(value):
    messages = _messages(value)
    return messages[0] if messages else VALIDATION_DETAIL
