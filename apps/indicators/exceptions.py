from rest_framework import status

from apps.common.exceptions import ApiError


class IndicatorFarmNotFound(ApiError):
    # También cubre la finca de otro productor o la que un empleado no trabaja: responder distinto
    # confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La finca no existe."
    default_code = "not_found"

    def __init__(self):
        super().__init__(fields={"farm": [self.default_detail]})
