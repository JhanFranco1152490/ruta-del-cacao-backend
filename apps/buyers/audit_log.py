"""Los compradores en la bitácora de cambios. Sus datos personales dicen que cambiaron, nunca su
valor: el historial no los guarda."""

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
)

from .models import Buyer, BuyerAuditEvent
from .services.audit import PERSONAL_FIELDS

TYPES = dict(Buyer.BuyerType.choices)
LABELS = {
    "name": "Nombre",
    "document_type": "Tipo de documento",
    "identity_document": "Número de documento",
    "buyer_type": "Tipo de cliente",
    "contact_name": "Contacto",
    "phone": "Teléfono",
    "email": "Correo",
    "is_active": "Activo",
}
KINDS = {"is_active": KIND_BOOL}


def events(producer_id, **filters):
    return audit_events(BuyerAuditEvent.objects.all(), producer_id, **filters)


def _label(event) -> str:
    # El nombre se lee del comprador, nunca del historial; si ya se eliminó, solo queda su tipo.
    if event.buyer is not None:
        return event.buyer.name
    return f"Comprador ({TYPES.get(event.buyer_type, event.buyer_type)})"


def describe(ids):
    found = BuyerAuditEvent.objects.filter(pk__in=ids).select_related("actor", "buyer")
    return [
        audit_entry(
            event,
            "buyer",
            record_id=event.buyer_ref,
            record_label=_label(event),
            record_deleted=event.buyer_id is None,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                personal=PERSONAL_FIELDS,
                names={"buyer_type": TYPES},
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
