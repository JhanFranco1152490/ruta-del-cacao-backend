"""El soporte de la factura de una venta: adjuntarlo, reemplazarlo, quitarlo y verlo."""

from django.db import transaction
from django.utils import timezone

from apps.common.files import JPEG, PDF, PNG, clean_file_name, detect_format
from apps.common.locks import lock_aggregate_root

from ..exceptions import (
    InvoiceFormatNotAllowed,
    InvoiceNotFound,
    InvoiceTooLarge,
    SaleNotFound,
    SaleVoided,
)
from ..models import INVOICE_MAX_BYTES, Sale, SaleAuditEvent
from .queries import get_sale, sale_scope

# Una factura escaneada o fotografiada, o el PDF que manda el comprador.
FORMATS = (PDF, JPEG, PNG)
NAME_MAX = 255
INVOICE_FIELDS = (
    "invoice",
    "invoice_name",
    "invoice_content_type",
    "invoice_size",
    "invoice_uploaded_at",
)


@transaction.atomic
def attach_invoice(actor, sale_id, uploaded) -> Sale:
    """Adjunta el soporte, o reemplaza el que había. El archivo ya llegó completo antes de esta
    función, así que el bloqueo de la finca no dura lo que tarda la subida por la red."""
    if uploaded.size > INVOICE_MAX_BYTES:
        raise InvoiceTooLarge()
    file_format = detect_format(uploaded, FORMATS)
    if file_format is None:
        raise InvoiceFormatNotAllowed()

    sale = _locked_open_sale(actor, sale_id)
    previous = sale.invoice.name if sale.invoice else None
    # El nombre en el almacenamiento es del servidor: nunca el que mandó el cliente. La hora lo
    # hace distinto del anterior, que se borra solo cuando la transacción se confirma.
    stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    sale.invoice.save(f"sales/{sale.pk}-{stamp}.{file_format.extension}", uploaded, save=False)
    sale.invoice_name = clean_file_name(uploaded.name, max_length=NAME_MAX, fallback="factura")
    sale.invoice_content_type = file_format.content_type
    sale.invoice_size = uploaded.size
    sale.invoice_uploaded_at = timezone.now()
    replaced = SaleAuditEvent.Action.INVOICE_REPLACED
    _save(actor, sale, replaced if previous else SaleAuditEvent.Action.INVOICE_ATTACHED)
    if previous:
        _delete_after_commit(sale.invoice.storage, previous)
    return get_sale(actor, sale.pk)


@transaction.atomic
def remove_invoice(actor, sale_id) -> None:
    """Quita el soporte. Sin soporte no hace nada."""
    sale = _locked_open_sale(actor, sale_id)
    if not sale.invoice:
        return
    storage, previous = sale.invoice.storage, sale.invoice.name
    sale.invoice = ""
    sale.invoice_name = ""
    sale.invoice_content_type = ""
    sale.invoice_size = None
    sale.invoice_uploaded_at = None
    _save(actor, sale, SaleAuditEvent.Action.INVOICE_REMOVED)
    _delete_after_commit(storage, previous)


def visible_invoice(actor, sale_id) -> Sale:
    """La venta con su soporte, si la cuenta la alcanza. Sin soporte, 404."""
    sale = Sale.objects.filter(pk=sale_id, **sale_scope(actor)).first()
    if sale is None:
        raise SaleNotFound()
    if not sale.invoice:
        raise InvoiceNotFound()
    return sale


def _locked_open_sale(actor, sale_id) -> Sale:
    sale, _farm = lock_aggregate_root(
        Sale, sale_id, root="farm", scope=sale_scope(actor), not_found=SaleNotFound
    )
    if sale.voided_at is not None:
        # Una venta anulada conserva su soporte, pero ya no cambia.
        raise SaleVoided()
    return sale


def _save(actor, sale, action) -> None:
    sale.version += 1
    sale.save(update_fields=[*INVOICE_FIELDS, "version", "updated_at"])
    SaleAuditEvent.record(
        sale=sale, actor=actor, action=action, changed_fields=INVOICE_FIELDS, version=sale.version
    )


def _delete_after_commit(storage, name) -> None:
    transaction.on_commit(lambda: storage.delete(name))
