from apps.common.audit import field_changes

from ..models import Lot, LotAuditEvent


def record_lot_event(
    *, lot: Lot, actor, action: str, before: dict | None = None, after: dict | None = None
) -> LotAuditEvent:
    changes = field_changes(before or {}, after or {})
    return LotAuditEvent.record(
        lot=lot if action != LotAuditEvent.Action.DELETED else None,
        lot_ref=lot.pk,
        code=lot.code,
        harvest_ref=lot.harvest_id,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=lot.version,
        changes=changes,
    )
