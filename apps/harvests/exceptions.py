from rest_framework import status

from apps.common.exceptions import ApiError


class HarvestNotFound(ApiError):
    # También cubre la cosecha de otro productor o de una finca que la cuenta no alcanza:
    # responder distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La cosecha no existe."
    default_code = "not_found"


class PlotNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La parcela no existe."
    default_code = "not_found"


class InvalidHarvest(ApiError):
    """Un dato que no cumple una regla de la cosecha, señalado en su campo."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Los datos enviados no son válidos."
    default_code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__(fields={field: [message]})


class HarvestIdConflict(ApiError):
    # Un `id` que ya usa otra cosecha: con otros datos, o de otro productor. No se dice cuál de
    # los dos, para no confirmar que existe.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una cosecha con este identificador."
    default_code = "harvest_id_conflict"


class PlotNotCharacterized(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La parcela no tiene siembras en su ficha: no se puede cosechar todavía."
    default_code = "plot_not_characterized"


class VarietyNotInPlot(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Esta variedad no está en la ficha de la parcela."
    default_code = "variety_not_in_plot"

    def __init__(self):
        super().__init__(fields={"variety_id": [self.default_detail]})


class CollectorNotAvailable(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Esta persona no puede ser la recolectora de una cosecha en esta parcela."
    default_code = "collector_not_available"

    def __init__(self):
        super().__init__(fields={"collector_id": [self.default_detail]})
