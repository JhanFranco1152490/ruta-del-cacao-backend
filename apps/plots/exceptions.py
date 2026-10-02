from rest_framework import status

from apps.common.exceptions import ApiError


class InvalidBoundary(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El polígono no es válido."
    default_code = "invalid_boundary"

    def __init__(self, reason: str):
        message = f"El polígono no es válido: {reason}."
        super().__init__(message, fields={"boundary": [message]})
