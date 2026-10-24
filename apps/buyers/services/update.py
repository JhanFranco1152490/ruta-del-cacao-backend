import copy
from functools import partial

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.common.audit import record_update_events
from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import BuyerNotFound, StaleBuyerVersion
from ..models import DOCUMENT_UNIQUE_CONSTRAINT, Buyer, BuyerAuditEvent
from ..usage import is_used
from .audit import record_buyer_audit_event
from .create import CONTENT_FIELDS, duplicate_error


@transaction.atomic
def update_buyer(actor, buyer_id, expected_version: int, data: dict) -> Buyer:
    """Edita un comprador, incluida su activación o desactivación. Todo se puede cambiar, también
    el documento: lo que apunta al comprador lo hace por su id. Sin cambios reales devuelve el
    comprador tal cual, sin subir la versión ni dejar historial."""
    try:
        buyer = Buyer.objects.select_for_update().get(pk=buyer_id, **owner_filter(actor))
    except Buyer.DoesNotExist:
        raise BuyerNotFound() from None

    if check_expected_version(
        buyer,
        expected_version,
        stale=lambda: StaleBuyerVersion(_with_usage(buyer)),
        already_applied=lambda: _already_applied(buyer, data),
    ):
        return _with_usage(buyer)

    before = {name: getattr(buyer, name) for name in CONTENT_FIELDS}
    _apply(buyer, data)
    # Valida el resultado y no solo lo que llegó: quitar el teléfono de quien no tiene correo se
    # responde aquí, y no como un choque con la base.
    buyer.full_clean(validate_unique=False, validate_constraints=False)
    changed = [name for name in CONTENT_FIELDS if getattr(buyer, name) != before[name]]
    if not changed:
        return _with_usage(buyer)

    save_next_version(
        buyer,
        changed,
        constraint=DOCUMENT_UNIQUE_CONSTRAINT,
        duplicate=lambda: duplicate_error(buyer),
    )
    record_update_events(
        partial(record_buyer_audit_event, buyer=buyer, actor=actor),
        changed,
        updated=BuyerAuditEvent.Action.UPDATED,
        status_changed=BuyerAuditEvent.Action.STATUS_CHANGED,
    )
    return _with_usage(buyer)


def _apply(buyer: Buyer, data: dict) -> None:
    for name, value in data.items():
        setattr(buyer, name, value)


def _already_applied(buyer: Buyer, data: dict) -> bool:
    """Si el comprador ya tiene lo que se pide: un doble clic reintenta aunque el servidor haya
    aplicado el cambio. Se compara después de limpiar como al guardar."""
    candidate = copy.copy(buyer)
    _apply(candidate, data)
    try:
        candidate.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError:
        return False
    return all(getattr(candidate, name) == getattr(buyer, name) for name in CONTENT_FIELDS)


def _with_usage(buyer: Buyer) -> Buyer:
    buyer.has_records = is_used(buyer)
    return buyer
