from functools import partial

from django.db import transaction

from apps.common.audit import record_update_events
from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import DuplicatePlotCode, StalePlotVersion
from ..models import Plot, PlotAuditEvent
from . import rules
from .audit import record_plot_audit_event
from .content import (
    CODE_UNIQUE_CONSTRAINT,
    UPDATABLE_FIELDS,
    apply_boundary,
    check_declared_area,
    current_boundary,
    matches,
)
from .queries import lock_plot


@transaction.atomic
def update_plot(actor, plot_id, expected_version: int, data: dict) -> Plot:
    """Edita, desactiva o reactiva una parcela. `boundary` reemplaza el contorno completo, y
    `None` lo quita.

    Las reglas de área y de superposición se revisan de nuevo solo si la parcela queda activa y
    cambia lo que ellas miran: su área, su contorno, o su estado al reactivarla. Desactivar no
    revisa nada, porque solo libera área.
    """
    plot = lock_plot(actor, plot_id)
    farm = plot.farm
    if check_expected_version(
        plot,
        expected_version,
        stale=lambda: StalePlotVersion(plot),
        already_applied=lambda: matches(plot, data, data.keys()),
    ):
        return plot
    rules.ensure_farm_active(farm)

    before = {name: getattr(plot, name) for name in (*UPDATABLE_FIELDS, "boundary")}
    for name in UPDATABLE_FIELDS:
        if name in data:
            setattr(plot, name, data[name])
    plot.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    if "boundary" in data:
        boundary = apply_boundary(plot, data["boundary"])
    else:
        boundary = current_boundary(plot)
        if boundary is not None and plot.area_hectares != before["area_hectares"]:
            check_declared_area(plot, plot.measured_area_hectares)
    # Se compara después de validar: un código que solo cambió en espacios no es un cambio.
    changed = [name for name in before if getattr(plot, name) != before[name]]
    if not changed:
        return plot

    reactivated = "is_active" in changed and plot.is_active
    if plot.is_active and (reactivated or "area_hectares" in changed):
        rules.check_available_area(farm, plot.area_hectares, exclude_plot_id=plot.pk)
    if boundary is not None and "boundary" in changed:
        rules.check_within_farm_reach(farm, boundary)
    if plot.is_active and boundary is not None and (reactivated or "boundary" in changed):
        rules.check_no_overlap(farm, boundary, exclude_plot_id=plot.pk)

    update_fields = list(changed)
    if "code" in changed:
        update_fields.append("code_normalized")
    if "boundary" in changed:
        update_fields.append("measured_area_hectares")
    save_next_version(
        plot, update_fields, constraint=CODE_UNIQUE_CONSTRAINT, duplicate=DuplicatePlotCode
    )
    record_update_events(
        partial(record_plot_audit_event, plot=plot, actor=actor),
        changed,
        updated=PlotAuditEvent.Action.UPDATED,
        status_changed=PlotAuditEvent.Action.STATUS_CHANGED,
    )
    return plot
