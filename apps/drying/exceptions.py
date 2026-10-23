from rest_framework import status

from apps.common.exceptions import ApiError


class DryingNotFound(ApiError):
    # También cubre el lote sin secado, el de otro productor o el de una finca fuera del alcance:
    # responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El secado no existe."
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


class FacilityNotFound(ApiError):
    # Una marquesina de otro productor no existe para este lote: responder distinto confirmaría
    # que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La marquesina no existe."
    default_code = "not_found"


class ResponsibleNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La cuenta no existe."
    default_code = "not_found"


class ResponsibleNotAvailable(ApiError):
    # Para responder por un secado hay que poder iniciarlo, llevar su bitácora y finalizarlo en la
    # finca del lote.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Esta cuenta no puede responder por un secado en la finca del lote."
    default_code = "responsible_not_available"

    def __init__(self):
        super().__init__(fields={"responsible_id": [self.default_detail]})


class EntryMoistureOutOfRange(ApiError):
    # No bloquea un caso real (un grano que llega más húmedo o más seco de lo esperado): pide que
    # quien registra lo confirme, y queda anotado en el secado.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = (
        "La humedad de entrada está fuera del rango esperado. Confírmala para iniciar de todos "
        "modos."
    )
    default_code = "entry_moisture_out_of_range"

    def __init__(self, minimum, maximum):
        super().__init__(
            fields={"entry_moisture_pct": [self.default_detail]},
            extra={"range": {"min": f"{minimum:.1f}", "max": f"{maximum:.1f}"}},
        )


class InvalidDrying(ApiError):
    """Un dato que no cumple una regla del secado, señalado en su campo."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Los datos enviados no son válidos."
    default_code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__(fields={field: [message]})


class DryingHasLogs(ApiError):
    # La fecha de inicio numera los días de la bitácora: cambiarla los renumeraría.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El secado ya tiene bitácora: su inicio ya no se corrige."
    default_code = "drying_has_logs"


class DryingNotInProgress(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El secado ya terminó."
    default_code = "drying_not_in_progress"


class StaleDryingVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Otra persona cambió este secado. Revisa los datos actuales antes de guardar."
    default_code = "stale_version"

    def __init__(self, lot_id):
        # La vista envía el vigente en `current` para que el formulario cargue sus valores.
        super().__init__()
        self.lot_id = lot_id
