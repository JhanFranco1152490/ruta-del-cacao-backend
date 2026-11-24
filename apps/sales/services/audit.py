from collections.abc import Iterable

from ..models import Sale, SaleAuditEvent


def record_sale_event(
    *, sale: Sale, actor, action: str, changed_fields: Iterable[str]
) -> SaleAuditEvent:
    return SaleAuditEvent.record(
        sale=sale,
        producer_ref=sale.producer_id,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        version=sale.version,
    )
