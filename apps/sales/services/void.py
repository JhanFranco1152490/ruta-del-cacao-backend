"""Anular una venta: los kilos de cada línea vuelven a la bodega y la venta queda en el
historial."""

from django.db import transaction
from django.utils import timezone

from apps.common.locks import lock_aggregate_root
from apps.common.versioning import check_expected_version

from ..exceptions import SaleNotFound, SaleVoided, StaleSaleVersion
from ..models import Sale, SaleAuditEvent
from .queries import get_sale, sale_scope

VOIDED_FIELDS = ("voided_at", "voided_by", "void_reason")


@transaction.atomic
def void_sale(actor, sale_id, expected_version: int, reason: str) -> Sale:
    """Anula la venta con su motivo. No se deshace: si se anuló por error, se registra de nuevo."""
    sale, _farm = lock_aggregate_root(
        Sale, sale_id, root="farm", scope=sale_scope(actor), not_found=SaleNotFound
    )
    if sale.voided_at is not None:
        raise SaleVoided()
    check_expected_version(
        sale, expected_version, stale=lambda: StaleSaleVersion(get_sale(actor, sale.pk))
    )

    for line in sale.lines.select_related("stock_exit__lot"):
        line.stock_exit.void_for_sale(actor, reason)

    sale.voided_by = actor
    sale.voided_at = timezone.now()
    sale.void_reason = reason
    sale.version += 1
    sale.save(update_fields=[*VOIDED_FIELDS, "version", "updated_at"])
    SaleAuditEvent.record(
        sale=sale,
        actor=actor,
        action=SaleAuditEvent.Action.VOIDED,
        changed_fields=VOIDED_FIELDS,
        version=sale.version,
    )
    return get_sale(actor, sale.pk)
