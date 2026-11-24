"""Los lotes en la bitácora de cambios."""

from apps.common.contracts.audit_log import AuditSource, audit_changes, audit_entry, audit_events

from .choices import LotStatus
from .models import LotAuditEvent

LABELS = {"status": "Estado"}
NAMES = {"status": dict(LotStatus.choices)}


def events(producer_id, **filters):
    return audit_events(LotAuditEvent.objects.all(), producer_id, **filters)


def describe(ids):
    found = LotAuditEvent.objects.filter(pk__in=ids).select_related("actor")
    return [
        audit_entry(
            event,
            "lot",
            record_id=event.lot_ref,
            # El código de la copia: sirve también si el lote ya se eliminó.
            record_label=event.code,
            record_deleted=event.lot_id is None,
            changes=audit_changes(
                event.changes,
                changed_fields=event.changed_fields,
                labels=LABELS,
                names=NAMES,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
