from dataclasses import asdict

from django.db import transaction

from apps.common.audit import field_changes

from ..baseline import DRYING_BASELINE
from ..fields import PERCENT_DECIMAL_PLACES
from ..models import PostharvestParametersAuditEvent
from .queries import ParametersState, parameters_state
from .read import as_drying_parameters
from .save import lock_parameters, record_event


def reset_parameters(actor, producer_id, expected_version) -> ParametersState:
    """Vuelve a la línea base borrando la fila: sin ella, el productor usa la línea base. El
    historial guarda los valores que había, para poder escribirlos otra vez si fue un error."""
    with transaction.atomic():
        producer_id, parameters = lock_parameters(actor, producer_id, expected_version)
        if parameters is None:
            return parameters_state(producer_id)
        changes = field_changes(
            asdict(as_drying_parameters(parameters)),
            asdict(DRYING_BASELINE),
            decimal_places=PERCENT_DECIMAL_PLACES,
        )
        parameters.delete()
        record_event(producer_id, actor, PostharvestParametersAuditEvent.Action.RESET, 0, changes)
        return parameters_state(producer_id)
