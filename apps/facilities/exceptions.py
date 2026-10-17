from rest_framework import status

from apps.common.exceptions import ApiError


class FacilityNotFound(ApiError):
    # También cubre el elemento de otro productor o de una finca fuera del alcance: responder
    # distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El elemento no existe."
    default_code = "not_found"
