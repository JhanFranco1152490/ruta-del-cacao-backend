"""Las parcelas en la bitácora de cambios."""

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
)

from .models import PlotAuditEvent

LABELS = {
    "name": "Nombre",
    "area_hectares": "Área declarada (ha)",
    "measured_area_hectares": "Área medida (ha)",
    "boundary": "Polígono",
    "is_active": "Activa",
}
KINDS = {
    "area_hectares": KIND_NUMBER,
    "measured_area_hectares": KIND_NUMBER,
    "is_active": KIND_BOOL,
}
# El polígono no se muestra como valor: basta saber que cambió.
NOT_SHOWN = ("boundary",)


def events(producer_id, **filters):
    return audit_events(PlotAuditEvent.objects.all(), producer_id, **filters)


def _label(event) -> str:
    # El código de la copia: sirve también si la parcela ya se eliminó.
    plot = event.plot
    if plot is None or not plot.name:
        return event.plot_code
    return f"{event.plot_code} · {plot.name}"


def describe(ids):
    found = PlotAuditEvent.objects.filter(pk__in=ids).select_related("actor", "plot")
    return [
        audit_entry(
            event,
            "plot",
            record_id=event.plot_ref,
            record_label=_label(event),
            record_deleted=event.plot_id is None,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                not_shown=NOT_SHOWN,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
