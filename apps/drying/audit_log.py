"""El secado en la bitácora de cambios: el proceso de un lote y su bitácora diaria."""

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    KIND_DATETIME,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
    names_by_id,
    referenced_ids,
)
from apps.common.serializers import full_name

from .models import DryingProcess, DryingProcessAuditEvent, Weather

# Los modelos de las otras apps se toman de las relaciones: ninguna app importa de otra.
Facility = DryingProcess._meta.get_field("facility").related_model
Account = DryingProcess._meta.get_field("responsible").related_model

LABELS = {
    "facility_id": "Marquesina",
    "started_at": "Inicio",
    "entry_moisture_pct": "Humedad de entrada (%)",
    "entry_moisture_out_of_range": "Humedad de entrada fuera del rango",
    "responsible_id": "Responsable",
    "ended_at": "Fin",
    "final_moisture_pct": "Humedad final (%)",
    "dry_weight_kg": "Peso seco (kg)",
    "yield_pct": "Rendimiento (%)",
    "total_sun_hours": "Horas de sol en total",
    "measured_at": "Hora de la medición",
    "moisture_pct": "Humedad (%)",
    "sun_hours": "Horas de sol",
    "shade_hours": "Horas de sombra",
    "turn_count": "Volteos",
    "turn_frequency_hours": "Cada cuántas horas se volteó",
    "weather": "Clima",
    "notes": "Notas",
}
NUMBERS = (
    "entry_moisture_pct",
    "final_moisture_pct",
    "dry_weight_kg",
    "yield_pct",
    "total_sun_hours",
    "moisture_pct",
    "sun_hours",
    "shade_hours",
    "turn_count",
    "turn_frequency_hours",
)
KINDS = {
    **{field: KIND_NUMBER for field in NUMBERS},
    "started_at": KIND_DATETIME,
    "ended_at": KIND_DATETIME,
    "measured_at": KIND_DATETIME,
    "entry_moisture_out_of_range": KIND_BOOL,
}


def events(producer_id, **filters):
    return audit_events(DryingProcessAuditEvent.objects.all(), producer_id, **filters)


def _label(event) -> str:
    # Un registro de la bitácora se nombra dentro de su lote: el registro es el secado del lote.
    label = f"Lote {event.process.lot.code}"
    return f"{label} · bitácora" if event.log_ref is not None else label


def describe(ids):
    found = list(
        DryingProcessAuditEvent.objects.filter(pk__in=ids).select_related("actor", "process__lot")
    )
    names = {
        "facility_id": names_by_id(
            Facility, referenced_ids(found, "facility_id"), lambda facility: facility.name
        ),
        "responsible_id": names_by_id(Account, referenced_ids(found, "responsible_id"), full_name),
        "weather": dict(Weather.choices),
    }
    return [
        audit_entry(
            event,
            "drying",
            record_id=event.process_id,
            record_label=_label(event),
            # Un secado no se elimina; una bitácora eliminada es una acción, no el registro.
            record_deleted=False,
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
