from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from ..models import Buyer, BuyerAuditEvent


def record_buyer_audit_event(
    *,
    buyer: Buyer,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
) -> BuyerAuditEvent:
    """Deja un evento con los nombres de los campos que cambiaron, sin sus valores."""
    return BuyerAuditEvent.record(
        buyer=buyer,
        buyer_ref=buyer.pk,
        buyer_type=buyer.buyer_type,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        version=buyer.version,
    )
