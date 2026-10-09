from rest_framework import status

from apps.common.exceptions import ApiError


class ActivityNotFound(ApiError):
    # También cubre la actividad de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La actividad no existe."
    default_code = "not_found"


class PlotNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La parcela no existe."
    default_code = "not_found"


class InvalidActivity(ApiError):
    """Un dato que no cumple una regla de la actividad, señalado en su campo."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Los datos enviados no son válidos."
    default_code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__(fields={field: [message]})


class ActivityIdConflict(ApiError):
    # Un `id` que ya usa otra actividad: con otro contenido, o de otro productor. No se dice cuál
    # de los dos, para no confirmar que existe.
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Ya existe una actividad con este identificador."
    default_code = "validation_error"

    def __init__(self):
        super().__init__(fields={"id": [self.default_detail]})


# Mismos códigos que usa la app de parcelas: el cliente decide por el código, no por quién lo
# lanzó.
class FarmInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La finca está inactiva: no se pueden programar actividades en sus parcelas."
    default_code = "farm_inactive"


class PlotInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La parcela está inactiva: no se pueden programar actividades en ella."
    default_code = "plot_inactive"


class ActivityTypeNotAllowed(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = (
        "El control fitosanitario no se programa aquí: se crea desde un monitoreo con hallazgos."
    )
    default_code = "activity_type_not_allowed"

    def __init__(self):
        super().__init__(fields={"activity_type": [self.default_detail]})


class AssigneeNotAvailable(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El responsable debe ser una cuenta activa del productor de la parcela."
    default_code = "assignee_not_available"

    def __init__(self):
        super().__init__(fields={"assignee_id": [self.default_detail]})
