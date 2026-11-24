"""La fermentación en la bitácora de cambios: el proceso de un lote y sus volteos."""

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

from .models import FermentationProcess, FermentationProcessAuditEvent

# Los modelos de las otras apps se toman de las relaciones: ninguna app importa de otra.
Facility = FermentationProcess._meta.get_field("facility").related_model
Account = FermentationProcess._meta.get_field("responsible").related_model

LABELS = {
    "facility_id": "Cajón",
    "started_at": "Inicio",
    "responsible_id": "Responsable",
    "over_capacity": "Supera la capacidad del cajón",
    "ended_at": "Fin",
    "end_notes": "Notas al finalizar",
    "turned_at": "Hora del volteo",
    "temperature_c": "Temperatura (°C)",
    "ph": "pH",
    "notes": "Notas",
}
KINDS = {
    "started_at": KIND_DATETIME,
    "ended_at": KIND_DATETIME,
    "turned_at": KIND_DATETIME,
    "over_capacity": KIND_BOOL,
    "temperature_c": KIND_NUMBER,
    "ph": KIND_NUMBER,
}


def events(producer_id, **filters):
    return audit_events(FermentationProcessAuditEvent.objects.all(), producer_id, **filters)


def _label(event) -> str:
    # Un volteo se nombra dentro de su lote: el registro es la fermentación del lote.
    label = f"Lote {event.process.lot.code}"
    return f"{label} · volteo" if event.turn_ref is not None else label


def describe(ids):
    found = list(
        FermentationProcessAuditEvent.objects.filter(pk__in=ids).select_related(
            "actor", "process__lot"
        )
    )
    names = {
        "facility_id": names_by_id(
            Facility, referenced_ids(found, "facility_id"), lambda facility: facility.name
        ),
        "responsible_id": names_by_id(Account, referenced_ids(found, "responsible_id"), full_name),
    }
    return [
        audit_entry(
            event,
            "fermentation",
            record_id=event.process_id,
            record_label=_label(event),
            # Una fermentación no se elimina; un volteo eliminado es una acción, no el registro.
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
