from rest_framework import status

from apps.common.exceptions import ApiError


class QualityLotNotFound(ApiError):
    # También cubre el lote que todavía no está Seco, el de otro productor y el de una finca fuera
    # del alcance: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El lote no existe."
    default_code = "not_found"
