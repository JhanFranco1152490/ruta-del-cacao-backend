from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from apps.common.audit import record_changes

from ..models import Plot, PlotAuditEvent

# Lo que la bitácora muestra con su valor. El polígono no: es grande, y basta saber que cambió.
VALUE_FIELDS = ("name", "area_hectares", "measured_area_hectares", "is_active")
WITHOUT_VALUE = ("boundary",)


def record_plot_audit_event(
    *,
    plot: Plot,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
    before: dict | None = None,
) -> PlotAuditEvent:
    """Deja el evento con los campos que cambiaron y su valor anterior y nuevo (`before` es lo que
    tenía la parcela antes de una edición)."""
    changed_fields = list(changed_fields)
    return PlotAuditEvent.record(
        plot=plot,
        plot_ref=plot.pk,
        plot_code=plot.code,
        producer_ref=plot.farm.producer_id,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        area_hectares=plot.area_hectares,
        measured_area_hectares=plot.measured_area_hectares,
        changes=record_changes(
            plot,
            value_fields=VALUE_FIELDS,
            changed_fields=changed_fields,
            before=before,
            created=action == PlotAuditEvent.Action.CREATED,
            deleted=action == PlotAuditEvent.Action.DELETED,
            exclude=WITHOUT_VALUE,
        ),
    )
