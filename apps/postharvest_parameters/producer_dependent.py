from apps.common.contracts.producer_dependents import ProducerDependent

from .models import PostharvestParameters, PostharvestParametersAuditEvent


def _parameters_of(producer):
    return PostharvestParameters.objects.filter(pk=producer.pk)


def _delete_all(producer, actor) -> None:
    # Configuración y no datos del negocio: se van con el productor creado por error, también su
    # historial, que no tiene a quién pertenecer sin él.
    _parameters_of(producer).delete()
    PostharvestParametersAuditEvent.objects.filter(producer_id=producer.pk).delete()


parameters_dependent = ProducerDependent(
    name="postharvest_parameters",
    # Nunca impiden eliminar al productor: ningún lote depende de ellos.
    important_record=lambda producer: None,
    count=lambda producer: _parameters_of(producer).count(),
    delete_all=_delete_all,
    models=(PostharvestParameters, PostharvestParametersAuditEvent),
)
