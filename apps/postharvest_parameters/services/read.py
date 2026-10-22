from apps.common.contracts.postharvest_parameters import DryingParameters

from ..baseline import DRYING_BASELINE
from ..fields import FIELDS
from ..models import PostharvestParameters


def as_drying_parameters(parameters: PostharvestParameters) -> DryingParameters:
    return DryingParameters(**{name: getattr(parameters, name) for name in FIELDS})


def current_parameters(producer_id) -> DryingParameters:
    """Los parámetros vigentes del productor: los guardados o, sin fila, la línea base."""
    parameters = PostharvestParameters.objects.filter(pk=producer_id).first()
    if parameters is None:
        return DRYING_BASELINE
    return as_drying_parameters(parameters)
