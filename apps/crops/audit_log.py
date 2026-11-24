"""La ficha de la parcela en la bitácora de cambios.

La ficha guarda en cada cambio su versión completa (`snapshot`), no los campos que cambiaron: lo
anterior de un cambio es la versión anterior de la misma parcela.
"""

from django.db.models import Q

from apps.common.contracts.audit_log import AuditSource, audit_changes, audit_entry, audit_events

from .choices import ManagementSystem, Propagation, ShadeType, Stage
from .models import PlotCharacterizationAuditEvent

LABELS = {
    "management_system": "Sistema de manejo",
    "shade_type": "Sombra",
    "plantings": "Siembras",
}
NAMES = {
    "management_system": dict(ManagementSystem.choices),
    "shade_type": dict(ShadeType.choices),
}
FIELDS = tuple(LABELS)


def events(producer_id, **filters):
    return audit_events(PlotCharacterizationAuditEvent.objects.all(), producer_id, **filters)


def planting_text(row: dict) -> str:
    """Una siembra como se lee: «CCN-51: 1800 árboles, sembrada en 2017-04, Injerto o clon,
    Producción estable». Las versiones viejas no guardaban la propagación ni la etapa."""
    parts = [f"{row['tree_count']} árboles", f"sembrada en {row['planting_date']}"]
    if row.get("propagation"):
        parts.append(dict(Propagation.choices).get(row["propagation"], row["propagation"]))
    if row.get("stage"):
        parts.append(dict(Stage.choices).get(row["stage"], row["stage"]))
    return f"{row['name']}: {', '.join(parts)}"


def _values(snapshot: dict | None) -> dict:
    if snapshot is None:
        return {}
    plantings = snapshot.get("plantings") or []
    return {
        "management_system": snapshot.get("management_system"),
        "shade_type": snapshot.get("shade_type"),
        "plantings": "; ".join(planting_text(row) for row in plantings) or None,
    }


def snapshot_changes(previous: dict | None, current: dict) -> dict:
    """Los campos que cambiaron de una versión a la siguiente, con el formato de `field_changes`.
    La primera versión no tiene anterior: trae lo que tenga, con el anterior vacío."""
    before, after = _values(previous), _values(current)
    return {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in FIELDS
        if before.get(field) != after.get(field)
    }


def _previous_snapshots(found) -> dict:
    """La versión anterior de cada evento, en una consulta."""
    wanted = Q(pk__in=[])
    for event in found:
        wanted |= Q(plot_id=event.plot_id, version=event.version - 1)
    rows = PlotCharacterizationAuditEvent.objects.filter(wanted).values(
        "plot_id", "version", "snapshot"
    )
    return {(row["plot_id"], row["version"]): row["snapshot"] for row in rows}


def describe(ids):
    found = list(
        PlotCharacterizationAuditEvent.objects.filter(pk__in=ids).select_related("actor", "plot")
    )
    previous = _previous_snapshots(found)
    return [
        audit_entry(
            event,
            "plot_characterization",
            record_id=event.plot_id,
            record_label=f"Ficha de {event.plot.code}",
            # La ficha se elimina con su parcela, y su historial con ella.
            record_deleted=False,
            changes=audit_changes(
                snapshot_changes(previous.get((event.plot_id, event.version - 1)), event.snapshot),
                labels=LABELS,
                names=NAMES,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
