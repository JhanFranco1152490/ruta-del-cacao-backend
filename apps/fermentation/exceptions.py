from rest_framework import status

from apps.common.exceptions import ApiError


class FermentationNotFound(ApiError):
    # También cubre el lote sin fermentación, el de otro productor y el de una finca que la cuenta
    # no alcanza: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La fermentación no existe."
    default_code = "not_found"


class LotNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El lote no existe."
    default_code = "not_found"


class LotInvalidStatus(ApiError):
    # El mismo código que responde la cadena de estados del lote cuando se le pide un paso que no
    # le toca: el cliente lo trata igual venga de donde venga.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El lote no está en el estado que esta operación necesita."
    default_code = "lot_invalid_status"

    def __init__(self, current_status: str):
        super().__init__(extra={"current_status": current_status})
