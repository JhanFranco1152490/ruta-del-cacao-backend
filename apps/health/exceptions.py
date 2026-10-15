from rest_framework import status

from apps.common.exceptions import ApiError


class PestDiseaseNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La plaga o enfermedad no existe."
    default_code = "not_found"


class DuplicatePestDiseaseName(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una plaga o enfermedad con este nombre."
    default_code = "duplicate_pest_disease_name"

    def __init__(self):
        super().__init__(fields={"name": [self.default_detail]})


class PestDiseaseInUse(ApiError):
    # Solo se lanza desde el admin: la API no elimina del catálogo.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La plaga o enfermedad ya se usó en algún monitoreo: desactívala."
    default_code = "pest_disease_in_use"


class MonitoringNotFound(ApiError):
    # También cubre el monitoreo de otro productor o de otra finca: responder distinto confirmaría
    # que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Este monitoreo ya no existe."
    default_code = "not_found"


class NotAMonitoring(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Esta actividad no es un monitoreo fitosanitario."
    default_code = "not_a_monitoring"


class MonitoringAlreadyRecorded(ApiError):
    # Mismo código que una realización repetida: el cliente decide por el código, no por quién lo
    # lanzó.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Este monitoreo ya se registró con otros datos."
    default_code = "activity_already_done"


class InvalidResult(ApiError):
    """Un dato del resultado que no cumple una regla, señalado en su campo."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Los datos enviados no son válidos."
    default_code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__(fields={field: [message]})


class PestDiseaseInactive(ApiError):
    # Lleva las afectadas para que el registro que esperaba en la cola marque cuáles cambiar.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Esta plaga o enfermedad ya no está disponible. Elige otra del catálogo."
    default_code = "pest_disease_inactive"

    def __init__(self, pest_disease_ids):
        super().__init__(
            fields={"detections": [self.default_detail]},
            extra={"pest_disease_ids": [str(pest_id) for pest_id in pest_disease_ids]},
        )
