from rest_framework import status

from apps.common.exceptions import ApiError


class InvalidResetToken(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El enlace no es válido o ya venció. Solicita uno nuevo."
    default_code = "invalid_reset_token"


class SessionExpired(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "La sesión venció. Inicia sesión de nuevo."
    default_code = "authentication_failed"


class InvalidCredentials(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Usuario o contraseña incorrectos."
    default_code = "invalid_credentials"


class AccountInactive(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "La cuenta está inactiva."
    default_code = "account_inactive"


class AccountLocked(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "La cuenta está bloqueada temporalmente. Intenta de nuevo en 15 minutos."
    default_code = "account_locked"
