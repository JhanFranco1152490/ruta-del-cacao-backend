from rest_framework import status

from apps.common.exceptions import ApiError

NOT_FOUND_TEXT = {
    "actor": "La cuenta no existe.",
    "producer": "El productor no existe.",
}


class AuditFilterNotFound(ApiError):
    # También cubre la cuenta de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Un filtro de la bitácora no existe."
    default_code = "not_found"

    def __init__(self, field: str):
        super().__init__(fields={field: [NOT_FOUND_TEXT[field]]})
