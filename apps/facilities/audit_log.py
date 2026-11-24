"""Los cajones y las marquesinas en la bitácora de cambios."""

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
    names_by_id,
    referenced_ids,
)

from .models import PostharvestFacility, PostharvestFacilityAuditEvent

# El modelo del lote se toma de la relación: ninguna app importa de otra.
Lot = PostharvestFacility._meta.get_field("current_lot").related_model

TYPES = dict(PostharvestFacility.FacilityType.choices)
LABELS = {
    "facility_type": "Tipo",
    "name": "Nombre",
    "capacity_kg": "Capacidad (kg)",
    "current_lot": "Lote",
    "is_active": "Activo",
}
KINDS = {"capacity_kg": KIND_NUMBER, "is_active": KIND_BOOL}


def events(producer_id, **filters):
    return audit_events(PostharvestFacilityAuditEvent.objects.all(), producer_id, **filters)


def _label(event) -> str:
    """«Cajón C-01»; si ya se eliminó, el nombre de la copia."""
    facility = event.facility
    if facility is None:
        return event.facility_name
    return f"{TYPES.get(facility.facility_type, '')} {event.facility_name}".strip()


def describe(ids):
    found = list(
        PostharvestFacilityAuditEvent.objects.filter(pk__in=ids).select_related(
            "actor", "facility"
        )
    )
    names = {
        "facility_type": TYPES,
        "current_lot": names_by_id(
            Lot, referenced_ids(found, "current_lot"), lambda lot: lot.code
        ),
    }
    return [
        audit_entry(
            event,
            "facility",
            record_id=event.facility_ref,
            record_label=_label(event),
            record_deleted=event.facility_id is None,
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
