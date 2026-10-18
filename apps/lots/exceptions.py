from rest_framework import status

from apps.common.exceptions import ApiError


class LotNotFound(ApiError):
    # También cubre el lote de otro productor o de una finca que la cuenta no alcanza: responder
    # distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El lote no existe."
    default_code = "not_found"


class HarvestNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La cosecha no existe."
    default_code = "not_found"


class HarvestAlreadyInLot(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Esta cosecha ya forma un lote."
    default_code = "harvest_already_in_lot"

    def __init__(self, current_lot):
        # La vista la envía en `current`, para que el cliente muestre el lote que ya existe.
        super().__init__()
        self.current_lot = current_lot


class LotIdConflict(ApiError):
    # Un `id` que ya usa otro lote: de otra cosecha, o de otro productor. No se dice cuál de los
    # dos, para no confirmar que existe.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe un lote con este identificador."
    default_code = "lot_id_conflict"


class LotInvalidStatus(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El lote no está en el estado que esta operación necesita."
    default_code = "lot_invalid_status"

    def __init__(self, current_status: str):
        super().__init__(extra={"current_status": current_status})


class StaleLotVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Otra persona cambió este lote. Revisa los datos actuales antes de guardar."
    default_code = "stale_version"

    def __init__(self, current_lot):
        super().__init__()
        self.current_lot = current_lot
