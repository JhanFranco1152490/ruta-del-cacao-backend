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


class DetectionNotFound(ApiError):
    # También cubre la detección de otro productor o de otra finca, y un monitoreo sin presencia,
    # que no tiene detecciones.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Esta detección ya no existe."
    default_code = "not_found"


class ScheduleNotAllowed(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "No tienes permiso para programar controles."
    default_code = "permission_denied"


class DoneControlNotAllowed(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "No tienes permiso para registrar controles realizados."
    default_code = "permission_denied"


class ControlIdConflict(ApiError):
    # Un `id` que ya usa otro control con otro contenido, u otra actividad. No se dice cuál de los
    # dos, para no confirmar que existe.
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Ya existe una actividad con este identificador."
    default_code = "validation_error"

    def __init__(self):
        super().__init__(fields={"id": [self.default_detail]})


class PlannedInputInactive(ApiError):
    # Mismo código que usa la app de insumos.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Este insumo ya no está disponible. Elige otro del catálogo."
    default_code = "input_inactive"

    def __init__(self, input_id):
        super().__init__(
            fields={"planned_input_id": [self.default_detail]},
            extra={"input_ids": [str(input_id)]},
        )


class PlotNotFound(ApiError):
    # También cubre la parcela de otro productor o de otra finca: responder distinto confirmaría
    # que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La parcela no existe."
    default_code = "not_found"


# --- Evidencia ---


class EvidenceTargetNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Este registro ya no existe."
    default_code = "not_found"


class EvidenceNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Esta foto ya no existe."
    default_code = "not_found"


class EvidenceNotAllowed(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Solo se adjuntan fotos a un monitoreo o a un control fitosanitario."
    default_code = "evidence_not_allowed"


class EvidenceRequiresDone(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La evidencia se adjunta cuando el registro ya está realizado."
    default_code = "evidence_requires_done"


class EvidenceTooLarge(ApiError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "El archivo supera el tamaño máximo de 5 MB."
    default_code = "evidence_too_large"

    def __init__(self):
        super().__init__(fields={"file": [self.default_detail]})


class EvidenceFormatNotAllowed(ApiError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = "Formato no permitido. Puedes adjuntar fotos JPG o PNG."
    default_code = "evidence_format_not_allowed"

    def __init__(self):
        super().__init__(fields={"file": [self.default_detail]})


class EvidenceLimitReached(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya tiene 5 fotos, el máximo."
    default_code = "evidence_limit_reached"


class EvidenceIdConflict(ApiError):
    # Un `id` que ya usa otra foto de otro registro. No se dice de cuál.
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Ya existe una foto con este identificador."
    default_code = "validation_error"

    def __init__(self):
        super().__init__(fields={"id": [self.default_detail]})


class EvidenceDeleteNotAllowed(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Esta foto la elimina quien la subió, el capataz de la finca o el productor."
    default_code = "permission_denied"
