from collections.abc import Iterable

from django.contrib.auth.base_user import AbstractBaseUser

from apps.common.audit import record_changes

from ..models import Buyer, BuyerAuditEvent

# Lo que identifica o contacta a una persona: el historial dice que cambió, nunca su valor.
PERSONAL_FIELDS = (
    "name",
    "document_type",
    "identity_document",
    "contact_name",
    "phone",
    "email",
)
VALUE_FIELDS = ("buyer_type", "is_active")


def record_buyer_audit_event(
    *,
    buyer: Buyer,
    actor: AbstractBaseUser,
    action: str,
    changed_fields: Iterable[str] = (),
    before: dict | None = None,
) -> BuyerAuditEvent:
    """Deja el evento con los nombres de los campos que cambiaron y el valor anterior y nuevo de
    los que no son datos personales."""
    changed_fields = list(changed_fields)
    return BuyerAuditEvent.record(
        buyer=buyer,
        buyer_ref=buyer.pk,
        buyer_type=buyer.buyer_type,
        producer_ref=buyer.producer_id,
        actor=actor,
        action=action,
        changed_fields=changed_fields,
        version=buyer.version,
        changes=record_changes(
            buyer,
            value_fields=VALUE_FIELDS,
            changed_fields=changed_fields,
            before=before,
            created=action == BuyerAuditEvent.Action.CREATED,
            deleted=action == BuyerAuditEvent.Action.DELETED,
            exclude=PERSONAL_FIELDS,
        ),
    )
