from django.db import transaction

from apps.common.db import has_dependent_rows
from apps.common.plot_dependents import registered_dependents
from apps.common.versioning import check_expected_version

from ..exceptions import PlotHasRecords, StalePlotVersion
from ..models import Plot, PlotAuditEvent
from . import rules
from .audit import record_plot_audit_event
from .queries import lock_plot


@transaction.atomic
def delete_plot(actor, plot_id, expected_version: int) -> None:
    """Elimina una parcela creada por error. Solo si nada depende de ella (cultivos, capturas,
    lotes): la que ya se usa se desactiva. Libera su área y su historial se conserva, con el
    borrado registrado en él."""
    plot = lock_plot(actor, plot_id)
    check_expected_version(plot, expected_version, stale=lambda: StalePlotVersion(plot))
    # Con la finca inactiva sus parcelas quedan congeladas, también para eliminarlas: al
    # reactivarla vuelven tal como estaban.
    rules.ensure_farm_active(plot.farm)
    if has_business_records(plot):
        raise PlotHasRecords()
    remove_plot(plot, actor)


def has_business_records(plot: Plot) -> bool:
    """Si la parcela tiene algo importante: un dependiente registrado que lo considere así, o
    cualquier otra tabla que la apunte, salvo su auditoría. Así una tabla nueva bloquea el borrado
    sin que nadie la agregue a una lista."""
    dependents = registered_dependents()
    if any(dependent.important_record(plot) for dependent in dependents):
        return True
    handled = tuple(model for dependent in dependents for model in dependent.models)
    return has_dependent_rows(plot, ignore=(PlotAuditEvent, *handled))


def remove_plot(plot: Plot, actor) -> None:
    """Elimina la parcela con lo que se va con ella, y deja el rastro. Quien llama ya comprobó que
    no tiene registros."""
    for dependent in registered_dependents():
        dependent.delete_all(plot, actor)
    record_plot_audit_event(plot=plot, actor=actor, action=PlotAuditEvent.Action.DELETED)
    plot.delete()
