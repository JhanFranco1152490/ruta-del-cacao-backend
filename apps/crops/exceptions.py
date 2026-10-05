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


class PlotNotFound(ApiError):
    # También cubre la parcela de otro productor: responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La parcela no existe."
    default_code = "not_found"


class CharacterizationNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La parcela no tiene caracterización."
    default_code = "not_found"


# Mismo código que usa la app de parcelas: el cliente decide por el código, no por quién lo
# lanzó.
class FarmInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = (
        "La finca está inactiva: no se puede modificar la caracterización de sus parcelas."
    )
    default_code = "farm_inactive"


class PlotInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La parcela está inactiva: no se puede modificar su caracterización."
    default_code = "plot_inactive"


class UnknownVariety(ApiError):
    # Un 400 y no un 404: la cola del dispositivo lee un 404 como un registro eliminado y
    # descartaría la ficha. Así llega a la bandeja de errores y la persona elige otra variedad.
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La variedad elegida no existe en el catálogo."
    default_code = "validation_error"

    def __init__(self):
        super().__init__(fields={"plantings": [self.default_detail]})


class DensityTooHigh(ApiError):
    # Un 422 y no un 400: depende del área de la parcela, que el cuerpo de la petición no trae.
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La densidad de siembra no es posible."
    default_code = "density_too_high"

    def __init__(self, density, limit):
        message = (
            f"Con {density:,} árboles/ha la densidad no es posible: el máximo es {limit:,}. "
            "Revisa el número de árboles o el área de la parcela."
        ).replace(",", ".")
        super().__init__(fields={"plantings": [message]})


class VarietyInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La variedad está desactivada: no se puede agregar a una caracterización."
    default_code = "variety_inactive"

    def __init__(self, names):
        message = f"Variedad desactivada: {', '.join(names)}. Elige otra del catálogo."
        super().__init__(fields={"plantings": [message]})


class StaleCharacterizationVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La caracterización fue modificada. Revisa los cambios antes de guardar."
    default_code = "stale_version"

    def __init__(self, current_characterization):
        # `None` si la parcela no tiene ficha: la vista lo envía así en `current`.
        super().__init__()
        self.current_characterization = current_characterization
