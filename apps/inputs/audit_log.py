"""Los insumos en la bitácora de cambios."""

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
)

from .models import AgriculturalInput, AgriculturalInputAuditEvent

LABELS = {
    "name": "Nombre",
    "input_type": "Tipo",
    "unit": "Unidad",
    "package_type": "Presentación",
    "package_size": "Contenido del empaque",
    "is_active": "Activo",
}
KINDS = {"package_size": KIND_NUMBER, "is_active": KIND_BOOL}
NAMES = {
    "input_type": dict(AgriculturalInput.InputType.choices),
    "unit": dict(AgriculturalInput.Unit.choices),
    "package_type": dict(AgriculturalInput.PackageType.choices),
}


def events(producer_id, **filters):
    return audit_events(AgriculturalInputAuditEvent.objects.all(), producer_id, **filters)


def describe(ids):
    found = AgriculturalInputAuditEvent.objects.filter(pk__in=ids).select_related("actor")
    return [
        audit_entry(
            event,
            "input",
            record_id=event.input_ref,
            # El nombre de la copia: sirve también si el insumo ya se eliminó.
            record_label=event.input_name,
            record_deleted=event.input_id is None,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                names=NAMES,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
