from rest_framework import status

from apps.common.exceptions import ApiError


class QualityLotNotFound(ApiError):
    # También cubre el lote que todavía no está Seco, el de otro productor y el de una finca fuera
    # del alcance: responder distinto confirmaría que existe.
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


class StaleQualityVersion(ApiError):
    # La versión del lote (al evaluar) o de la evaluación (al corregirla) cambió desde que se leyó.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Otra persona cambió este lote. Revisa los datos actuales antes de guardar."
    default_code = "stale_version"

    def __init__(self, lot_id):
        # La vista envía el vigente en `current` para que el formulario cargue sus valores.
        super().__init__()
        self.lot_id = lot_id


class QualitySumExceeds100(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La suma no puede pasar de 100 %"
    default_code = "quality_sum_exceeds_100"

    def __init__(self, total):
        super().__init__(
            fields={"non_field_errors": [self.default_detail]},
            extra={"total_pct": f"{total:.1f}"},
        )
