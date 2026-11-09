"""Lo que se lee de las existencias: el lote con su ingreso, sus saldos y sus salidas."""

from decimal import Decimal

from django.db.models import Count, F, Prefetch, Q, QuerySet, Sum

from apps.common.ownership import owner_filter

from ..choices import Grade
from ..exceptions import StockLotNotFound
from ..models import StockBalance, StockExit
from .lots import CLASSIFIED, STOCK_STATUSES, Lot, lot_scope

# Cómo se puede ordenar la consulta de existencias: de la clave de la API a los campos de la base.
ORDERINGS = {
    "lot": ("lot__code",),
    "grade": ("grade",),
    "quantity": ("quantity_kg",),
    "location": ("location",),
    "entry_date": ("lot__stock_entry__entry_date",),
}
DEFAULT_ORDERING = ("-lot__stock_entry__entry_date", "lot__code", "grade")


def visible_stock_lots(actor) -> QuerySet:
    """Los lotes Clasificado o En bodega que `actor` alcanza, con todo lo que muestra su
    representación: lo de uno a uno en la misma consulta y saldos y salidas precargados."""
    return (
        Lot.objects.filter(**lot_scope(actor), status__in=STOCK_STATUSES)
        .select_related(
            "harvest__plot__farm",
            "classification",
            "stock_entry__warehouse",
            "stock_entry__entered_by",
            "stock_entry__corrected_by",
        )
        .prefetch_related(
            "stock_balances",
            Prefetch(
                "stock_exits",
                queryset=StockExit.objects.select_related("created_by", "voided_by").order_by(
                    "-created_at", "id"
                ),
            ),
        )
    )


def get_lot_stock(actor, lot_id):
    lot = visible_stock_lots(actor).filter(pk=lot_id).first()
    if lot is None:
        raise StockLotNotFound()
    return lot


def pending_entry_lots(actor, filters: dict) -> QuerySet:
    """Los lotes Clasificado con algo que ingresar, del que se clasificó primero. Uno cuyo peso
    seco se fue entero en descarte no tiene qué ingresar y no aparece."""
    lots = (
        Lot.objects.filter(**lot_scope(actor), status=CLASSIFIED)
        .select_related("harvest__plot__farm", "classification")
        .annotate(kilograms=F("classification__g1_kg") + F("classification__g2_kg"))
        .filter(kilograms__gt=0)
    )
    if "farm" in filters:
        lots = lots.filter(harvest__plot__farm_id=filters["farm"])
    if term := (filters.get("search") or "").strip():
        lots = lots.filter(code__icontains=term)
    if actor.is_superuser and "producer" in filters:
        lots = lots.filter(harvest__plot__farm__producer_id=filters["producer"])
    return lots.order_by("classification__classified_at", "code")


def visible_balances(actor) -> QuerySet:
    """Las existencias disponibles (más de 0 kg) de las fincas que `actor` alcanza: una por lote y
    calibre. Un calibre que se agotó sigue en la base, pero no cuenta como disponible."""
    scope = owner_filter(
        actor, "lot__harvest__plot__farm__producer_id", farm="lot__harvest__plot__farm_id"
    )
    return StockBalance.objects.filter(**scope, quantity_kg__gt=0).select_related(
        "lot__harvest__plot__farm", "lot__stock_entry", "warehouse"
    )


def filter_balances(actor, filters: dict) -> QuerySet:
    """Con los filtros de la pantalla: finca, bodega, calibre, parte de la ubicación y parte del
    código del lote, sin distinguir mayúsculas. `producer` solo lo usa la cuenta técnica."""
    balances = visible_balances(actor)
    if "farm" in filters:
        balances = balances.filter(lot__harvest__plot__farm_id=filters["farm"])
    if "warehouse" in filters:
        balances = balances.filter(warehouse_id=filters["warehouse"])
    if "grade" in filters:
        balances = balances.filter(grade=filters["grade"])
    if term := (filters.get("location") or "").strip():
        balances = balances.filter(location__icontains=term)
    if term := (filters.get("search") or "").strip():
        balances = balances.filter(lot__code__icontains=term)
    if actor.is_superuser and "producer" in filters:
        balances = balances.filter(lot__harvest__plot__farm__producer_id=filters["producer"])
    return balances


def list_stock(actor, filters: dict) -> QuerySet:
    ordering = filters.get("ordering")
    if ordering is None:
        return filter_balances(actor, filters).order_by(*DEFAULT_ORDERING)
    descending = ordering.startswith("-")
    fields = ORDERINGS[ordering.lstrip("-")]
    ordered = [f"-{field}" if descending else field for field in fields]
    return filter_balances(actor, filters).order_by(*ordered, "lot__code", "grade")


def stock_summary(actor, filters: dict) -> dict:
    """Los kilos disponibles de G1 y de G2 y cuántos lotes tienen existencias, entre las filas que
    cumplen los filtros."""
    totals = (
        filter_balances(actor, filters)
        .order_by()
        .aggregate(
            g1_kg=Sum("quantity_kg", filter=Q(grade=Grade.G1)),
            g2_kg=Sum("quantity_kg", filter=Q(grade=Grade.G2)),
            lots=Count("lot_id", distinct=True),
        )
    )
    return {
        "g1_kg": totals["g1_kg"] or Decimal("0.0"),
        "g2_kg": totals["g2_kg"] or Decimal("0.0"),
        "lots": totals["lots"],
    }


def stock_locations(actor, warehouse_id) -> list[str]:
    """Las ubicaciones con existencias en una bodega, sin repetir y en orden alfabético; lo que se
    ingresó sin ubicación no cuenta."""
    return list(
        visible_balances(actor)
        .filter(warehouse_id=warehouse_id)
        .exclude(location="")
        .order_by("location")
        .values_list("location", flat=True)
        .distinct()
    )
