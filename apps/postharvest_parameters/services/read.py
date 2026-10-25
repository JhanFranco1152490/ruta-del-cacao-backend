from decimal import Decimal

from apps.common.contracts.postharvest_parameters import DryingParameters, FermentationParameters

from ..baseline import BASELINE_VALUES, DRYING_BASELINE, FERMENTATION_BASELINE
from ..fields import DECIMAL_PLACES, DRYING_FIELDS, FERMENTATION_FIELDS, FIELDS
from ..models import PostharvestParameters


def stored_values(parameters: PostharvestParameters) -> dict:
    """Los veintiún valores guardados, con los nombres de la lista única."""
    return {name: getattr(parameters, name) for name in FIELDS}


def values_or_baseline(parameters: PostharvestParameters | None) -> dict:
    return BASELINE_VALUES if parameters is None else stored_values(parameters)


def with_api_decimals(values: dict) -> dict:
    """Los decimales con las cifras que entrega la API (55,0 de humedad, 4,00 de pH), para que el
    historial los guarde igual sin importar de dónde vinieron."""
    return {
        name: (
            Decimal(value).quantize(Decimal(1).scaleb(-DECIMAL_PLACES[FIELDS[name]]))
            if FIELDS[name] in DECIMAL_PLACES
            else value
        )
        for name, value in values.items()
    }


def as_drying_parameters(parameters: PostharvestParameters) -> DryingParameters:
    return DryingParameters(**{name: getattr(parameters, name) for name in DRYING_FIELDS})


def as_fermentation_parameters(parameters: PostharvestParameters) -> FermentationParameters:
    return FermentationParameters(
        **{name: getattr(parameters, name) for name in FERMENTATION_FIELDS}
    )


def current_parameters(producer_id) -> DryingParameters:
    """Los de secado vigentes del productor: los guardados o, sin fila, la línea base."""
    parameters = PostharvestParameters.objects.filter(pk=producer_id).first()
    if parameters is None:
        return DRYING_BASELINE
    return as_drying_parameters(parameters)


def current_fermentation_parameters(producer_id) -> FermentationParameters:
    """Los de fermentación vigentes, con la misma regla."""
    parameters = PostharvestParameters.objects.filter(pk=producer_id).first()
    if parameters is None:
        return FERMENTATION_BASELINE
    return as_fermentation_parameters(parameters)
