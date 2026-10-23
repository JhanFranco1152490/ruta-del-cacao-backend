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


class FacilityNotFound(ApiError):
    # Un cajón de otro productor no existe para este lote: responder distinto confirmaría que
    # existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El cajón no existe."
    default_code = "not_found"


class ResponsibleNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La cuenta no existe."
    default_code = "not_found"


class ResponsibleNotAvailable(ApiError):
    # Para responder por una fermentación hay que poder iniciarla, voltear y finalizarla en la
    # finca del lote.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Esta cuenta no puede responder por una fermentación en la finca del lote."
    default_code = "responsible_not_available"

    def __init__(self):
        super().__init__(fields={"responsible_id": [self.default_detail]})


class LotExceedsCapacity(ApiError):
    # No bloquea un caso real (un cajón que se llena de más): pide que quien registra lo confirme.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = (
        "El lote supera la capacidad del cajón. Confírmalo para iniciar de todos modos."
    )
    default_code = "lot_exceeds_capacity"

    def __init__(self, capacity_kg, green_weight_kg):
        super().__init__(
            extra={
                "capacity_kg": f"{capacity_kg:.1f}",
                "green_weight_kg": f"{green_weight_kg:.1f}",
            }
        )


class InvalidFermentation(ApiError):
    """Un dato que no cumple una regla de la fermentación, señalado en su campo."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Los datos enviados no son válidos."
    default_code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__(fields={field: [message]})


class FermentationHasTurns(ApiError):
    # El inicio decide cuándo tocaba el primer volteo, y ningún volteo puede quedar antes de él.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La fermentación ya tiene volteos: su inicio ya no se corrige."
    default_code = "fermentation_has_turns"


class FermentationNotInProgress(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La fermentación ya terminó."
    default_code = "fermentation_not_in_progress"


class StaleFermentationVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Otra persona cambió esta fermentación. Revisa los datos actuales antes de guardar."
    )
    default_code = "stale_version"

    def __init__(self, lot_id):
        # La vista envía la vigente en `current` para que el formulario cargue sus valores.
        super().__init__()
        self.lot_id = lot_id


class TurnNotFound(ApiError):
    # También cubre el volteo de otra fermentación.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El volteo no existe."
    default_code = "not_found"


class TurnIdConflict(ApiError):
    # Un `id` que ya usa otro volteo, con otros datos o de otra fermentación. No se dice cuál, para
    # no confirmar que existe.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe un volteo con este identificador."
    default_code = "turn_id_conflict"


class DuplicateTurnTime(ApiError):
    # Dos registros del mismo minuto son el mismo volteo, enviado dos veces.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya hay un volteo registrado a esa hora."
    default_code = "duplicate_turn_time"

    def __init__(self, existing_id=None, number=None):
        extra = None
        if existing_id is not None:
            extra = {"existing": {"id": str(existing_id), "number": number}}
        super().__init__(fields={"turned_at": [self.default_detail]}, extra=extra)


class StaleTurnVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Otra persona cambió este volteo. Revisa los datos actuales antes de guardar."
    default_code = "stale_version"

    def __init__(self, turn):
        super().__init__()
        self.current_turn = turn


class FermentationWithoutTurns(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Registre al menos un volteo para finalizar"
    default_code = "fermentation_without_turns"
