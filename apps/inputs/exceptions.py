from rest_framework import status

from apps.common.exceptions import ApiError


class InputNotFound(ApiError):
    # También cubre el insumo de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El insumo no existe."
    default_code = "not_found"


class StaleInputVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El insumo fue modificado. Revisa los cambios antes de guardar."
    default_code = "stale_version"

    def __init__(self, current_input):
        super().__init__()
        self.current_input = current_input


class DuplicateInput(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe un insumo con este nombre y tipo."
    default_code = "duplicate_input"

    def __init__(self, existing=None):
        # El existente permite a la interfaz ofrecer verlo o, si está inactivo, activarlo.
        extra = None
        if existing is not None:
            extra = {
                "existing": {
                    "id": str(existing.pk),
                    "name": existing.name,
                    "input_type": existing.input_type,
                    "is_active": existing.is_active,
                }
            }
        super().__init__(fields={"name": [self.default_detail]}, extra=extra)


class InputHasRecords(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El insumo tiene registros asociados. Desactívalo en lugar de eliminarlo."
    default_code = "input_has_records"


class InputUnitLocked(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "No se puede cambiar: el insumo ya se usó en registros."
    default_code = "input_unit_locked"

    def __init__(self, field: str):
        super().__init__(fields={field: [self.default_detail]})


class ProducerInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El productor está inactivo."
    default_code = "producer_inactive"

    def __init__(self):
        super().__init__(fields={"producer_id": [self.default_detail]})
