from rest_framework import status

from apps.common.exceptions import ApiError


class PlotNotFound(ApiError):
    # También cubre la parcela de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La parcela no existe."
    default_code = "not_found"


class FarmNotFound(ApiError):
    # La finca de otro productor tampoco existe para quien registra una parcela.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La finca no existe."
    default_code = "not_found"


class FarmInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La finca está inactiva: no se pueden modificar sus parcelas."
    default_code = "farm_inactive"


class InvalidBoundary(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El polígono no es válido."
    default_code = "invalid_boundary"

    def __init__(self, reason: str):
        message = f"El polígono no es válido: {reason}."
        super().__init__(message, fields={"boundary": [message]})


class AreaMismatch(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El área declarada difiere más del 5 % del área dibujada."
    default_code = "area_mismatch"

    def __init__(self, measured_area_hectares):
        super().__init__(fields={"area_hectares": [self.default_detail]})
        # La vista la agrega al cuerpo para ofrecer usar el área calculada.
        self.measured_area_hectares = measured_area_hectares


class PlotAreaExceedsFarm(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El área ingresada supera el área disponible de la finca."
    default_code = "plot_area_exceeds_farm"

    def __init__(self):
        super().__init__(fields={"area_hectares": [self.default_detail]})


class PlotOverlap(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El polígono se superpone con otra parcela de la finca."
    default_code = "plot_overlap"

    def __init__(self, overlaps, suggested_boundary, suggested_measured_area_hectares):
        """`overlaps` es una lista de `(parcela, área invadida)`. La vista arma con ellos el
        cuerpo del error, con el contorno de cada vecina para dibujarla en el dispositivo."""
        codes = ", ".join(plot.code for plot, _ in overlaps)
        noun = "la parcela" if len(overlaps) == 1 else "las parcelas"
        super().__init__(fields={"boundary": [f"El polígono se superpone con {noun} {codes}."]})
        self.overlaps = overlaps
        self.suggested_boundary = suggested_boundary
        self.suggested_measured_area_hectares = suggested_measured_area_hectares


class DuplicatePlotCode(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una parcela con este código en la finca."
    default_code = "duplicate_plot_code"

    def __init__(self):
        super().__init__(fields={"code": [self.default_detail]})


class StalePlotVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La parcela fue modificada. Revisa los cambios antes de guardar."
    default_code = "stale_version"

    def __init__(self, current_plot):
        super().__init__()
        self.current_plot = current_plot


class PlotIdConflict(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El identificador ya pertenece a otra parcela."
    default_code = "plot_id_conflict"

    def __init__(self, current_plot=None):
        # Solo se adjunta la parcela cuando es del mismo productor: si es ajena, mostrarla
        # revelaría datos de otro productor.
        super().__init__()
        self.current_plot = current_plot
