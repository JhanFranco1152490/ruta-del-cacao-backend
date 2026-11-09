from rest_framework import status

from apps.common.exceptions import ApiError


class SaleNotFound(ApiError):
    # También cubre la venta de otro productor o de una finca que la cuenta no alcanza: responder
    # distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La venta no existe."
    default_code = "not_found"
