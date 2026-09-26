from rest_framework import status

from apps.common.exceptions import ApiError


class ProducerNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El productor no existe."
    default_code = "not_found"


class StaleVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La ficha fue modificada por otra persona. Recarga antes de guardar."
    default_code = "stale_version"


class DuplicateDocument(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El documento ya se encuentra registrado."
    default_code = "duplicate_document"

    def __init__(self, existing_producer_id=None):
        super().__init__(
            fields={"identity_document": [self.default_detail]},
            extra=(
                {"existing_producer_id": str(existing_producer_id)} if existing_producer_id else {}
            ),
        )
