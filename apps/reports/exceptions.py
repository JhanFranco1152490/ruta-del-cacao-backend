from rest_framework import status

from apps.common.exceptions import ApiError

NOT_FOUND_TEXT = {
    "farm": "La finca no existe.",
    "plot": "La parcela no existe.",
    "lot": "El lote no existe.",
    "producer": "El productor no existe.",
}


class ReportFilterNotFound(ApiError):
    # También cubre lo de otro productor o lo que un empleado no alcanza: responder distinto
    # confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Un filtro del reporte no existe."
    default_code = "not_found"

    def __init__(self, field: str):
        super().__init__(fields={field: [NOT_FOUND_TEXT[field]]})


class ReportTypeNotAllowed(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "No tienes permiso para consultar la información de este reporte."
    default_code = "permission_denied"


class ReportTooLarge(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El reporte tiene demasiadas filas. Acota el periodo, la finca o la parcela."
    default_code = "report_too_large"
