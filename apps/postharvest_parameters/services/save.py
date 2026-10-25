from django.apps import apps
from django.db import transaction

from apps.common.audit import field_changes
from apps.common.locks import lock_root_row
from apps.common.versioning import save_next_version

from ..exceptions import ProducerNotFound, StaleParameters
from ..models import PostharvestParameters, PostharvestParametersAuditEvent
from .queries import ParametersState, parameters_state, target_producer_id
from .read import values_or_baseline, with_api_decimals


def lock_parameters(actor, producer_id, expected_version):
    """Bloquea al productor, raíz de todo lo suyo, y devuelve `(id del productor, fila o None)`
    si la versión que leyó el cliente sigue siendo la vigente. Con el productor bloqueado, dos
    guardados no se pisan: el segundo espera y encuentra la versión que dejó el primero."""
    producer_id = target_producer_id(actor, producer_id)
    if lock_root_row(apps.get_model("producers", "Producer"), producer_id) is None:
        raise ProducerNotFound()
    parameters = PostharvestParameters.objects.filter(pk=producer_id).first()
    current_version = parameters.version if parameters is not None else 0
    if expected_version != current_version:
        raise StaleParameters(parameters_state(producer_id))
    return producer_id, parameters


def record_event(producer_id, actor, action, version, changes):
    PostharvestParametersAuditEvent.record(
        action=action,
        changed_fields=changes,
        producer_id=producer_id,
        actor=actor,
        version=version,
        changes=changes,
    )


def save_parameters(actor, producer_id, expected_version, values: dict) -> ParametersState:
    """Guarda los veintiún valores juntos. La primera vez crea la fila y el historial compara
    contra la línea base, que era lo que se usaba; después, solo registra lo que cambió."""
    with transaction.atomic():
        producer_id, parameters = lock_parameters(actor, producer_id, expected_version)
        changes = field_changes(
            with_api_decimals(values_or_baseline(parameters)), with_api_decimals(values)
        )
        if parameters is None:
            parameters = PostharvestParameters.objects.create(
                producer_id=producer_id, updated_by=actor, **values
            )
        elif not changes:
            return parameters_state(producer_id)
        else:
            for name in changes:
                setattr(parameters, name, values[name])
            parameters.updated_by = actor
            save_next_version(parameters, [*changes, "updated_by"])
        record_event(
            producer_id,
            actor,
            PostharvestParametersAuditEvent.Action.UPDATED,
            parameters.version,
            changes,
        )
        return parameters_state(producer_id)
