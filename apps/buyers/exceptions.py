from rest_framework import status

from apps.common.exceptions import ApiError


class BuyerNotFound(ApiError):
    # También cubre el comprador de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El comprador no existe."
    default_code = "not_found"


class StaleBuyerVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El comprador fue modificado. Revisa los cambios antes de guardar."
    default_code = "stale_version"

    def __init__(self, current_buyer):
        super().__init__()
        self.current_buyer = current_buyer


class BuyerHasRecords(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "No se puede eliminar: el comprador tiene ventas registradas. Puedes desactivarlo."
    )
    default_code = "buyer_has_records"


class ProducerInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El productor está inactivo."
    default_code = "producer_inactive"

    def __init__(self):
        super().__init__(fields={"producer_id": [self.default_detail]})


class DuplicateBuyerDocument(ApiError):
    status_code = status.HTTP_409_CONFLICT
    # Sin el número: es un dato personal cuando el comprador es una persona natural.
    default_detail = "Ya tienes registrado un comprador con este documento."
    default_code = "duplicate_document"

    def __init__(self, existing=None):
        # El existente permite a la interfaz ofrecer verlo o, si está inactivo, activarlo.
        extra = None
        if existing is not None:
            extra = {
                "existing": {
                    "id": str(existing.pk),
                    "name": existing.name,
                    "is_active": existing.is_active,
                }
            }
        super().__init__(fields={"identity_document": [self.default_detail]}, extra=extra)
