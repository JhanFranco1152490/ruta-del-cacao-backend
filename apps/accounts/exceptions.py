from rest_framework import status

from apps.common.exceptions import ApiError


class InvalidResetToken(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El enlace no es válido o ya venció. Solicita uno nuevo."
    default_code = "invalid_reset_token"
