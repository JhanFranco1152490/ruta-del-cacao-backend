from django.db import transaction

from apps.common.db import has_dependent_rows

from ..exceptions import PlotHasRecords, StalePlotVersion
from ..models import PlotAuditEvent
from . import rules
from .audit import record_plot_audit_event
from .queries import lock_plot


@transaction.atomic
def delete_plot(actor, plot_id, expected_version: int) -> None:
    """Elimina una parcela creada por error. Solo si nada depende de ella (cultivos, capturas,
    lotes): la que ya se usa se desactiva. Libera su área y su historial se conserva, con el
    borrado registrado en él."""
    plot = lock_plot(actor, plot_id)
    if plot.version != expected_version:
        raise StalePlotVersion(plot)
    # Con la finca inactiva sus parcelas quedan congeladas, también para eliminarlas: al
    # reactivarla vuelven tal como estaban.
    rules.ensure_farm_active(plot.farm)
    if has_dependent_rows(plot, ignore=(PlotAuditEvent,)):
        raise PlotHasRecords()
    record_plot_audit_event(plot=plot, actor=actor, action=PlotAuditEvent.Action.DELETED)
    plot.delete()
