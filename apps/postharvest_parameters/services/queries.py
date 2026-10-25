from dataclasses import dataclass, field
from datetime import datetime

from django.apps import apps

from apps.common.exceptions import ProducerRequired

from ..baseline import BASELINE_VALUES
from ..exceptions import InvalidParameters, ProducerNotFound
from ..models import PostharvestParameters
from .read import stored_values


@dataclass(frozen=True)
class ParametersState:
    """Lo que ve quien consulta: los parámetros vigentes y de dónde salen."""

    producer_id: object
    values: dict
    is_default: bool
    version: int
    updated_at: datetime | None
    updated_by: object | None
    baseline: dict = field(default_factory=lambda: BASELINE_VALUES)


def target_producer_id(actor, producer_id=None):
    """El productor cuyos parámetros se leen o se cambian: el de la cuenta, o el que nombra la
    cuenta técnica, que no tiene uno propio. Otra cuenta no elige: lo que mande se ignora."""
    if not actor.is_superuser:
        if actor.producer_id is None:
            raise ProducerRequired()
        return actor.producer_id
    if producer_id is None:
        raise InvalidParameters("producer", "Indica de qué productor son los parámetros.")
    producer_model = apps.get_model("producers", "Producer")
    if not producer_model.objects.filter(pk=producer_id).exists():
        raise ProducerNotFound()
    return producer_id


def parameters_state(producer_id) -> ParametersState:
    parameters = (
        PostharvestParameters.objects.select_related("updated_by").filter(pk=producer_id).first()
    )
    if parameters is None:
        return ParametersState(
            producer_id=producer_id,
            values=BASELINE_VALUES,
            is_default=True,
            version=0,
            updated_at=None,
            updated_by=None,
        )
    return ParametersState(
        producer_id=producer_id,
        values=stored_values(parameters),
        is_default=False,
        version=parameters.version,
        updated_at=parameters.updated_at,
        updated_by=parameters.updated_by,
    )


def get_parameters(actor, producer_id=None) -> ParametersState:
    return parameters_state(target_producer_id(actor, producer_id))
