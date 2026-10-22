from rest_framework import status

from apps.common.exceptions import ApiError


class ProducerNotFound(ApiError):
    # Solo la cuenta técnica nombra un productor: las demás leen siempre el suyo.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El productor no existe."
    default_code = "not_found"


class InvalidParameters(ApiError):
    """Un dato que no cumple una regla de los parámetros, señalado en su campo."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Los datos enviados no son válidos."
    default_code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__(fields={field: [message]})
