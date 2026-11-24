"""Las cosechas en la bitácora de cambios."""

from datetime import date

from apps.common.contracts.audit_log import (
    KIND_DATE,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
    names_by_id,
    referenced_ids,
)
from apps.common.serializers import full_name

from .models import Harvest, HarvestAuditEvent

# Los modelos de las otras apps se toman de las relaciones: ninguna app importa de otra.
Plot = Harvest._meta.get_field("plot").related_model
Variety = Harvest._meta.get_field("variety").related_model
Account = Harvest._meta.get_field("collector").related_model

LABELS = {
    "harvest_date": "Fecha de la cosecha",
    "green_weight_kg": "Peso en verde (kg)",
    "variety_id": "Variedad",
    "collector_id": "Recolector",
    "characterization_version": "Versión de la ficha",
}
KINDS = {
    "harvest_date": KIND_DATE,
    "green_weight_kg": KIND_NUMBER,
    "characterization_version": KIND_NUMBER,
}


def events(producer_id, **filters):
    return audit_events(HarvestAuditEvent.objects.all(), producer_id, **filters)


def _harvest_date(event):
    if event.harvest is not None:
        return event.harvest.harvest_date
    # Ya se eliminó: la fecha que guardó el evento.
    values = (event.changes or {}).get("harvest_date") or {}
    stored = values.get("before") or values.get("after")
    return date.fromisoformat(stored) if stored else None


def _label(event, plots: dict) -> str:
    """«Cosecha del 14/11/2026 · P01»."""
    day = _harvest_date(event)
    label = f"Cosecha del {day:%d/%m/%Y}" if day else "Cosecha"
    plot = plots.get(str(event.plot_ref))
    return f"{label} · {plot}" if plot else label


def describe(ids):
    found = list(HarvestAuditEvent.objects.filter(pk__in=ids).select_related("actor", "harvest"))
    plots = names_by_id(Plot, {event.plot_ref for event in found}, lambda plot: plot.code)
    names = {
        "variety_id": names_by_id(
            Variety, referenced_ids(found, "variety_id"), lambda variety: variety.name
        ),
        "collector_id": names_by_id(Account, referenced_ids(found, "collector_id"), full_name),
    }
    return [
        audit_entry(
            event,
            "harvest",
            record_id=event.harvest_ref,
            record_label=_label(event, plots),
            record_deleted=event.harvest_id is None,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                names=names,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
