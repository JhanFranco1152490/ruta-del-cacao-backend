from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from ..models import Plot, PlotAuditEvent


def record_plot_audit_event(
    *,
    plot: Plot,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
) -> PlotAuditEvent:
    return PlotAuditEvent.record(
        plot=plot,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        area_hectares=plot.area_hectares,
        measured_area_hectares=plot.measured_area_hectares,
    )
