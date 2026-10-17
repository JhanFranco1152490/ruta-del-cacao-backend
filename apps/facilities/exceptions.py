from rest_framework import status

from apps.common.exceptions import ApiError


class FacilityNotFound(ApiError):
    # También cubre el elemento de otro productor o de una finca fuera del alcance: responder
    # distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El elemento no existe."
    default_code = "not_found"


class FarmNotFound(ApiError):
    # También cubre la finca de otro productor o una en la que el empleado no trabaja.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La finca no existe."
    default_code = "not_found"


class FarmInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La finca está inactiva: no se le pueden registrar cajones ni marquesinas."
    default_code = "farm_inactive"


class DuplicateFacilityName(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe un elemento con este nombre o código en la finca."
    default_code = "duplicate_facility_name"

    def __init__(self, existing=None):
        # El existente permite a la interfaz ofrecer verlo o, si está inactivo, activarlo.
        extra = None
        if existing is not None:
            extra = {
                "existing": {
                    "id": str(existing.pk),
                    "name": existing.name,
                    "facility_type": existing.facility_type,
                    "is_active": existing.is_active,
                }
            }
        super().__init__(fields={"name": [self.default_detail]}, extra=extra)


class FarmRequired(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Tu cuenta no tiene una finca asignada."
    default_code = "permission_denied"


class StaleFacilityVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Otra persona cambió este elemento. Revisa los datos actuales antes de guardar."
    )
    default_code = "stale_version"

    def __init__(self, current_facility):
        super().__init__()
        self.current_facility = current_facility


class FacilityFieldsLocked(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "No se puede cambiar: el elemento ya se usó en un proceso."
    default_code = "facility_fields_locked"

    def __init__(self, field: str):
        super().__init__(fields={field: [self.default_detail]})
