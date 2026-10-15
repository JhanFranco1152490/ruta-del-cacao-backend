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
