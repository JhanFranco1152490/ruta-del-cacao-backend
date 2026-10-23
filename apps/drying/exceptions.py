from rest_framework import status

from apps.common.exceptions import ApiError


class DryingNotFound(ApiError):
    # También cubre el lote sin secado, el de otro productor o el de una finca fuera del alcance:
    # responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El secado no existe."
    default_code = "not_found"
