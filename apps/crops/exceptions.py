from rest_framework import status

from apps.common.exceptions import ApiError


class VarietyNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La variedad no existe."
    default_code = "not_found"


class DuplicateVarietyName(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una variedad con este nombre."
    default_code = "duplicate_variety_name"

    def __init__(self):
        super().__init__(fields={"name": [self.default_detail]})
