from django.db import transaction
from django.db.models import ProtectedError

from apps.common.ownership import owner_filter
from apps.common.versioning import check_expected_version

from ..exceptions import BuyerHasRecords, BuyerNotFound, StaleBuyerVersion
from ..models import Buyer, BuyerAuditEvent
from ..usage import is_used
from .audit import record_buyer_audit_event


@transaction.atomic
def delete_buyer(actor, buyer_id, expected_version: int) -> None:
    """Elimina un comprador registrado por error. Solo si ningún registro lo usa; el que tiene
    ventas se desactiva. Su historial se conserva y el borrado queda registrado en él."""
    try:
        buyer = Buyer.objects.select_for_update().get(pk=buyer_id, **owner_filter(actor))
    except Buyer.DoesNotExist:
        raise BuyerNotFound() from None
    check_expected_version(buyer, expected_version, stale=lambda: _stale(buyer))
    remove_buyer(buyer, actor)


def remove_buyer(buyer: Buyer, actor) -> None:
    """Elimina `buyer` y deja el rastro. Quien llama ya validó quién puede hacerlo: aquí solo se
    aplica la regla. Si algo lo usa, `BuyerHasRecords` y no se toca nada."""
    if is_used(buyer):
        raise BuyerHasRecords()
    record_buyer_audit_event(buyer=buyer, actor=actor, action=BuyerAuditEvent.Action.DELETED)
    try:
        buyer.delete()
    except ProtectedError:
        # Un registro que apunta al comprador apareció entre la revisión y el borrado: la base es
        # la garantía final. La transacción de quien llama deshace también el evento.
        raise BuyerHasRecords() from None


def _stale(buyer: Buyer) -> StaleBuyerVersion:
    buyer.has_records = is_used(buyer)
    return StaleBuyerVersion(buyer)
