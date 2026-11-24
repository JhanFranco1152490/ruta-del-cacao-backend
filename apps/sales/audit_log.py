"""Las ventas en la bitácora de cambios: lo registrado, la anulación y el soporte."""

from apps.common.contracts.audit_log import (
    KIND_DATE,
    KIND_DATETIME,
    KIND_NUMBER,
    AuditSource,
    audit_changes,
    audit_entry,
    audit_events,
    names_by_id,
    referenced_ids,
)
from apps.common.serializers import full_name

from .models import Grade, Sale, SaleAuditEvent

# Los modelos de las otras apps se toman de las relaciones: ninguna app importa de otra.
Farm = Sale._meta.get_field("farm").related_model
Buyer = Sale._meta.get_field("buyer").related_model
Account = Sale._meta.get_field("voided_by").related_model

GRADES = dict(Grade.choices)
LABELS = {
    "farm": "Finca",
    "buyer": "Comprador",
    "sale_date": "Fecha de la venta",
    "notes": "Notas",
    "lines": "Lotes vendidos",
    "voided_at": "Anulada el",
    "voided_by": "Anulada por",
    "void_reason": "Motivo de la anulación",
    "invoice_name": "Soporte",
    "invoice_content_type": "Tipo de archivo del soporte",
    "invoice_size": "Tamaño del soporte (bytes)",
    "invoice_uploaded_at": "Soporte cargado el",
}
KINDS = {
    "sale_date": KIND_DATE,
    "voided_at": KIND_DATETIME,
    "invoice_size": KIND_NUMBER,
    "invoice_uploaded_at": KIND_DATETIME,
}
# El nombre con que se guarda el archivo del soporte es interno.
SKIP = ("invoice",)


def events(producer_id, **filters):
    return audit_events(SaleAuditEvent.objects.all(), producer_id, **filters)


def line_text(row: dict) -> str:
    """«000123-F02-P05-260314-1 · G1 · 20.0 kg a $ 18.500 por kg»."""
    price = f"$ {row['price_per_kg']:,}".replace(",", ".")
    grade = GRADES.get(row["grade"], row["grade"])
    return f"{row['lot']} · {grade} · {row['quantity_kg']} kg a {price} por kg"


def _with_lines_as_text(changes: dict) -> dict:
    lines = changes.get("lines")
    if not lines:
        return changes

    def text(rows):
        return "; ".join(line_text(row) for row in rows) if rows else None

    return {**changes, "lines": {side: text(lines.get(side)) for side in ("before", "after")}}


def describe(ids):
    found = list(SaleAuditEvent.objects.filter(pk__in=ids).select_related("actor", "sale"))
    names = {
        "farm": names_by_id(Farm, referenced_ids(found, "farm"), lambda farm: farm.name),
        "buyer": names_by_id(Buyer, referenced_ids(found, "buyer"), lambda buyer: buyer.name),
        "voided_by": names_by_id(Account, referenced_ids(found, "voided_by"), full_name),
    }
    return [
        audit_entry(
            event,
            "sale",
            record_id=event.sale_id,
            # Como se muestra en Ventas (`V-0012`). Una venta no se elimina: se anula.
            record_label=event.sale.code,
            record_deleted=False,
            changes=audit_changes(
                _with_lines_as_text(event.changes or {}),
                changed_fields=event.changed_fields,
                labels=LABELS,
                kinds=KINDS,
                names=names,
                skip=SKIP,
            ),
        )
        for event in found
    ]


SOURCE = AuditSource(events=events, describe=describe)
