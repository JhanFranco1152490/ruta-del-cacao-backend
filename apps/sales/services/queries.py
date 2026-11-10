"""Lo que se lee de las ventas. Todo el alcance pasa por aquí: el productor alcanza las ventas de
todas sus fincas, un empleado las de las fincas en las que trabaja y la cuenta técnica las de
cualquiera."""

from decimal import Decimal

from django.db.models import CharField, Count, DecimalField, Prefetch, Q, QuerySet, Sum, Value
from django.db.models.functions import Cast, Coalesce, Lower

from apps.common.ownership import owner_filter

from ..exceptions import SaleNotFound
from ..models import Grade, Sale, SaleLine

# El modelo del comprador se toma de la relación: ninguna app importa de otra.
Buyer = Sale._meta.get_field("buyer").related_model
ZERO_KG = Value(Decimal("0.0"), output_field=DecimalField(max_digits=9, decimal_places=1))


def sale_scope(actor) -> dict:
    return owner_filter(actor, "producer_id", farm="farm_id")


def _kilos(grade, prefix=""):
    return Coalesce(Sum(f"{prefix}quantity_kg", filter=Q(**{f"{prefix}grade": grade})), ZERO_KG)


def visible_sales(actor) -> QuerySet[Sale]:
    """Las ventas que `actor` alcanza, con lo que muestra su representación en la misma consulta:
    la finca, el comprador, las cuentas y los kilos de cada calibre y el total de sus líneas."""
    return (
        Sale.objects.filter(**sale_scope(actor))
        .select_related("farm", "buyer", "created_by", "voided_by")
        .annotate(
            g1_kg=_kilos(Grade.G1, "lines__"),
            g2_kg=_kilos(Grade.G2, "lines__"),
            total=Coalesce(Sum("lines__subtotal"), 0),
        )
    )


def list_sales(actor, filters: dict) -> QuerySet[Sale]:
    """Las ventas del periodo, de la más reciente a la más antigua, con los filtros de la lista."""
    sales = visible_sales(actor).filter(sale_date__range=(filters["from"], filters["to"]))
    # Solo la cuenta técnica elige de qué productor ver: para las demás el alcance ya es el suyo.
    if filters.get("producer") and actor.is_superuser:
        sales = sales.filter(producer_id=filters["producer"])
    if filters.get("farm"):
        sales = sales.filter(farm_id=filters["farm"])
    if filters.get("buyer"):
        sales = sales.filter(buyer_id=filters["buyer"])
    if filters.get("status") == Sale.Status.REGISTERED:
        sales = sales.filter(voided_at__isnull=True)
    elif filters.get("status") == Sale.Status.VOIDED:
        sales = sales.filter(voided_at__isnull=False)
    if digits := "".join(char for char in filters.get("search", "") if char.isdigit()):
        # Se busca por el número: `V-0012`, `0012` y `12` encuentran la misma venta.
        sales = sales.annotate(number_text=Cast("number", CharField())).filter(
            number_text__contains=digits.lstrip("0") or "0"
        )
    return sales.order_by("-sale_date", "-number")


def sales_summary(actor, filters: dict) -> dict:
    """Las cifras de la franja: lo vendido en las ventas registradas que cumplen los filtros. Las
    anuladas no suman."""
    sales = list_sales(actor, {**filters, "status": Sale.Status.REGISTERED})
    lines = SaleLine.objects.filter(sale__in=sales.values("pk"))
    totals = lines.aggregate(
        g1_kg=_kilos(Grade.G1),
        g2_kg=_kilos(Grade.G2),
        total=Coalesce(Sum("subtotal"), 0),
    )
    return {**totals, "sales": sales.aggregate(count=Count("pk"))["count"]}


def get_sale(actor, sale_id) -> Sale:
    sale = (
        visible_sales(actor)
        .prefetch_related(Prefetch("lines", queryset=SaleLine.objects.select_related("lot")))
        .filter(pk=sale_id)
        .first()
    )
    if sale is None:
        raise SaleNotFound()
    return sale


def buyer_options(actor, *, producer=None) -> QuerySet:
    """Los compradores activos a los que `actor` puede venderles: los de su productor; la cuenta
    técnica, los del productor que nombra. Solo lo que el formulario muestra, sin su documento ni
    su contacto: registrar una venta no pide consultar el directorio."""
    buyers = Buyer.objects.filter(**owner_filter(actor), is_active=True)
    if producer is not None and actor.is_superuser:
        buyers = buyers.filter(producer_id=producer)
    return buyers.order_by(Lower("name"), "id").only("id", "name", "buyer_type")
