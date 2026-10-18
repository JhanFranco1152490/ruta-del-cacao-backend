"""Qué lotes y cosechas alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un
empleado lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from decimal import Decimal

from django.db.models import Count, QuerySet, Sum

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..choices import LotStatus
from ..exceptions import HarvestNotFound, LotNotFound
from ..models import Lot

# El modelo de la cosecha se toma de la relación y no de su app: ninguna app importa de otra.
Harvest = Lot._meta.get_field("harvest").related_model

LOT_SCOPE = {"field": "harvest__plot__farm__producer_id", "farm": "harvest__plot__farm_id"}


def visible_lots(actor) -> QuerySet[Lot]:
    return Lot.objects.filter(
        **owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"])
    ).select_related(
        "harvest__plot__farm__producer",
        "harvest__variety",
        "harvest__collector",
        "harvest__registered_by",
        "created_by",
    )


def filter_lots(actor, filters: dict) -> QuerySet[Lot]:
    """Los lotes que `actor` alcanza con los filtros de la lista: estado, finca, parcela, variedad,
    periodo de la fecha de cosecha y parte del código, sin distinguir mayúsculas. `producer` solo
    lo usa la cuenta técnica, que sin él ve los de todos."""
    lots = visible_lots(actor)
    if "status" in filters:
        lots = lots.filter(status=filters["status"])
    if "farm" in filters:
        lots = lots.filter(harvest__plot__farm_id=filters["farm"])
    if "plot" in filters:
        lots = lots.filter(harvest__plot_id=filters["plot"])
    if "variety" in filters:
        lots = lots.filter(harvest__variety_id=filters["variety"])
    if "from" in filters:
        lots = lots.filter(harvest__harvest_date__gte=filters["from"])
    if "to" in filters:
        lots = lots.filter(harvest__harvest_date__lte=filters["to"])
    if term := (filters.get("search") or "").strip():
        lots = lots.filter(code__icontains=term)
    if actor.is_superuser and "producer" in filters:
        lots = lots.filter(harvest__plot__farm__producer_id=filters["producer"])
    return lots


def list_lots(actor, filters: dict) -> QuerySet[Lot]:
    """Los lotes filtrados, del de cosecha más reciente al más antiguo."""
    return filter_lots(actor, filters).order_by("-harvest__harvest_date", "code")


def lot_summary(actor, filters: dict) -> list[dict]:
    """Cuántos lotes y cuántos kilos en verde hay en cada estado, con los demás filtros de la
    lista. El estado no filtra: el recuento es lo que permite elegirlo. Están todos los estados de
    la cadena, en orden, también los que no tienen lotes."""
    others = {key: value for key, value in filters.items() if key != "status"}
    rows = (
        filter_lots(actor, others)
        .order_by()
        .values("status")
        .annotate(count=Count("id"), green_weight_kg=Sum("harvest__green_weight_kg"))
    )
    by_status = {row["status"]: row for row in rows}
    return [
        {
            "status": status.value,
            "count": by_status.get(status.value, {}).get("count", 0),
            "green_weight_kg": by_status.get(status.value, {}).get("green_weight_kg")
            or Decimal("0"),
        }
        for status in LotStatus
    ]


def get_lot(actor, lot_id) -> Lot:
    lot = visible_lots(actor).filter(pk=lot_id).first()
    if lot is None:
        raise LotNotFound()
    return lot


def lock_harvest(actor, harvest_id):
    """La cosecha, con la finca de su parcela bloqueada hasta el final de la transacción, y con
    lo que el código del lote necesita (parcela, finca y productor) ya cargado."""
    harvest, _ = lock_aggregate_root(
        Harvest,
        harvest_id,
        root="plot__farm",
        scope=owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id"),
        not_found=HarvestNotFound,
    )
    return Harvest.objects.select_related("plot__farm__producer").get(pk=harvest.pk)


def lock_lot(actor, lot_id) -> Lot:
    """El lote, con la finca de su parcela bloqueada hasta el final de la transacción."""
    lock_aggregate_root(
        Lot,
        lot_id,
        root="harvest__plot__farm",
        scope=owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"]),
        not_found=LotNotFound,
    )
    return visible_lots(actor).get(pk=lot_id)
