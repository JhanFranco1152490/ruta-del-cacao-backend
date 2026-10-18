from rest_framework import status

from apps.common.exceptions import ApiError


class NotificationNotFound(ApiError):
    # También cubre la de otra persona o de una finca que ya no alcanza: responder distinto
    # confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La notificación no existe."
    default_code = "not_found"
