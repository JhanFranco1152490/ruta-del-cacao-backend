from rest_framework import status

from apps.common.exceptions import ApiError


class BuyerNotFound(ApiError):
    # También cubre el comprador de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El comprador no existe."
    default_code = "not_found"
