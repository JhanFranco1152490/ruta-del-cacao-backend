from rest_framework import status

from apps.common.exceptions import ApiError


class FarmNotFound(ApiError):
    # También cubre la finca de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La finca no existe."
    default_code = "not_found"


class ProducerRequired(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "La cuenta no está vinculada a un productor."
    default_code = "permission_denied"


class StaleFarmVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La finca fue modificada. Revisa los cambios antes de guardar."
    default_code = "stale_version"

    def __init__(self, current_farm):
        super().__init__()
        self.current_farm = current_farm


class DuplicateFarmName(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una finca con este nombre."
    default_code = "duplicate_farm_name"

    def __init__(self):
        super().__init__(fields={"name": ["El nombre debe ser único para el productor."]})


class FarmHasRecords(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La finca tiene registros asociados. Desactívala en lugar de eliminarla."
    default_code = "farm_has_records"


class FarmIdConflict(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El identificador ya pertenece a otra finca."
    default_code = "farm_id_conflict"

    def __init__(self, current_farm=None):
        # Solo se adjunta la finca cuando es del mismo productor: si es ajena, mostrarla
        # revelaría datos de otro productor.
        super().__init__()
        self.current_farm = current_farm


class LocationRequired(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La georreferenciación es obligatoria."
    default_code = "location_required"


class InvalidCoordinates(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Coordenadas no válidas."
    default_code = "invalid_coordinates"


class LocationOutsideOperatingArea(ApiError):
    # Distinto de `invalid_coordinates`: el punto existe, pero está fuera de la zona donde opera
    # la asociación.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La ubicación está fuera de Norte de Santander."
    default_code = "location_outside_operating_area"


class MunicipalityDepartmentMismatch(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El municipio no pertenece al departamento."
    default_code = "municipality_department_mismatch"

    def __init__(self):
        super().__init__(fields={"municipality_code": [self.default_detail]})
