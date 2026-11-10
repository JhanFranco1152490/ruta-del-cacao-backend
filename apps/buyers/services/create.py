from django.db import transaction

from apps.common.db import save_translating_unique
from apps.common.ownership import resolve_target_producer

from ..exceptions import DuplicateBuyerDocument, ProducerInactive
from ..models import DOCUMENT_UNIQUE_CONSTRAINT, Buyer, BuyerAuditEvent
from .audit import record_buyer_audit_event

CONTENT_FIELDS = (
    "name",
    "document_type",
    "identity_document",
    "buyer_type",
    "contact_name",
    "phone",
    "email",
    "is_active",
)


def existing_with_document(buyer: Buyer) -> Buyer | None:
    """El comprador del mismo productor con el mismo tipo y número de documento, si lo hay."""
    return (
        Buyer.objects.filter(
            producer_id=buyer.producer_id,
            document_type=buyer.document_type,
            identity_document=buyer.identity_document,
        )
        .exclude(pk=buyer.pk)
        .first()
    )


def duplicate_error(buyer: Buyer) -> DuplicateBuyerDocument:
    return DuplicateBuyerDocument(existing_with_document(buyer))


@transaction.atomic
def create_buyer(actor, data: dict) -> Buyer:
    """Registra un comprador en el directorio del productor de la sesión, o del que nombra la
    cuenta técnica. Queda activo."""
    data = dict(data)
    producer_id = resolve_target_producer(
        actor,
        data,
        Buyer._meta.get_field("producer").related_model,
        inactive=ProducerInactive,
    )
    buyer = Buyer(producer_id=producer_id, created_by=actor if actor.pk else None, **data)
    buyer.full_clean(validate_unique=False, validate_constraints=False)
    save_translating_unique(
        lambda: buyer.save(force_insert=True),
        constraint=DOCUMENT_UNIQUE_CONSTRAINT,
        duplicate=lambda: duplicate_error(buyer),
    )
    record_buyer_audit_event(
        buyer=buyer,
        actor=actor,
        action=BuyerAuditEvent.Action.CREATED,
        changed_fields=CONTENT_FIELDS,
    )
    buyer.has_records = False
    return buyer
