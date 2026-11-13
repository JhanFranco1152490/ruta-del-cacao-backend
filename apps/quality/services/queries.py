"""Qué lotes de calidad alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un empleado
lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import QualityLotNotFound
from ..models import QualityEvaluation

# El modelo del lote se toma de la relación y no de su app: ninguna app importa de otra.
Lot = QualityEvaluation._meta.get_field("lot").related_model

# Los estados del lote que esta app usa, tal como los guarda su campo.
DRIED = "dried"
EVALUATED = "evaluated"
CLASSIFIED = "classified"
DISCARDED = "discarded"
IN_WAREHOUSE = "in_warehouse"
# Un lote clasificado que bodega ya guardó sigue siendo un lote cerrado de calidad: el estado
# En bodega lo agrega bodega, pero la clasificación (y sus kilos de G1 y G2) es de esta app.
CLASSIFIED_STATUSES = (CLASSIFIED, IN_WAREHOUSE)
CLOSED_STATUSES = (*CLASSIFIED_STATUSES, DISCARDED)
QUALITY_STATUSES = (DRIED, EVALUATED, *CLOSED_STATUSES)

TO_EVALUATE = "to_evaluate"
VIEWS = {
    TO_EVALUATE: (DRIED,),
    "evaluated": (EVALUATED,),
    "closed": CLOSED_STATUSES,
}

# Quién cerró primero el lote: la clasificación o el descarte, según cuál tenga.
CLOSED_AT = Coalesce("classification__classified_at", "discard__discarded_at")
CLOSED_RESULTS = {"classified": CLASSIFIED_STATUSES, "discarded": (DISCARDED,)}

LOT_SCOPE = {"field": "harvest__plot__farm__producer_id", "farm": "harvest__plot__farm_id"}


def visible_lots(actor) -> QuerySet:
    """Los lotes Seco o posteriores que `actor` alcanza, con todo lo que muestra su
    representación en la misma consulta: son relaciones de uno a uno."""
    return Lot.objects.filter(
        **owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"]),
        status__in=QUALITY_STATUSES,
    ).select_related(
        "harvest__plot__farm",
        "drying",
        "quality_evaluation__evaluated_by",
        "quality_evaluation__corrected_by",
        "classification__classified_by",
        "discard__discarded_by",
    )


def filter_lots(actor, filters: dict) -> QuerySet:
    """Con los filtros de la pantalla menos la vista: finca y parte del código, sin distinguir
    mayúsculas. `producer` solo lo usa la cuenta técnica, que sin él ve los de todos."""
    lots = visible_lots(actor)
    if "farm" in filters:
        lots = lots.filter(harvest__plot__farm_id=filters["farm"])
    if term := (filters.get("search") or "").strip():
        lots = lots.filter(code__icontains=term)
    if actor.is_superuser and "producer" in filters:
        lots = lots.filter(harvest__plot__farm__producer_id=filters["producer"])
    return lots


def _day_start(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def closed_in_period(lots: QuerySet, filters: dict) -> QuerySet:
    """Los lotes cerrados (Clasificado, ya En bodega o Descartado) con su fecha de cierre en
    `closed_at`, y solo los que cerraron entre `closed_from` y `closed_to`, ambos días incluidos,
    en la hora de Bogotá.
    """
    lots = lots.filter(status__in=CLOSED_STATUSES).annotate(closed_at=CLOSED_AT)
    if start := filters.get("closed_from"):
        lots = lots.filter(closed_at__gte=_day_start(start))
    if end := filters.get("closed_to"):
        lots = lots.filter(closed_at__lt=_day_start(end + timedelta(days=1)))
    return lots


def list_quality_lots(actor, filters: dict) -> QuerySet:
    """Los lotes de una vista: por evaluar, del que se secó primero; evaluados, del que se evaluó
    primero; cerrados, del que se clasificó o descartó más recientemente. Los cerrados además se
    filtran por resultado y por periodo de cierre."""
    view = filters.get("view", TO_EVALUATE)
    lots = filter_lots(actor, filters)
    if view == "closed":
        lots = closed_in_period(lots, filters)
        if "result" in filters:
            lots = lots.filter(status__in=CLOSED_RESULTS[filters["result"]])
        return lots.order_by("-closed_at", "code")
    lots = lots.filter(status__in=VIEWS[view])
    if view == TO_EVALUATE:
        return lots.order_by("drying__ended_at", "code")
    return lots.order_by("quality_evaluation__evaluated_at", "code")


def quality_summary(actor, filters: dict) -> dict:
    """Las cifras de la pantalla, con los filtros de la lista menos la vista."""
    month_start = timezone.make_aware(
        datetime.combine(timezone.localdate().replace(day=1), time.min)
    )
    totals = (
        filter_lots(actor, filters)
        .order_by()
        .aggregate(
            to_evaluate=Count("pk", filter=Q(status=DRIED)),
            to_evaluate_kg=Sum("drying__dry_weight_kg", filter=Q(status=DRIED)),
            evaluated=Count("pk", filter=Q(status=EVALUATED)),
            discarded_this_month=Count(
                "pk", filter=Q(status=DISCARDED, discard__discarded_at__gte=month_start)
            ),
        )
    )
    totals["to_evaluate_kg"] = totals["to_evaluate_kg"] or Decimal("0")
    return totals


def closed_totals() -> dict:
    """Las sumas de los lotes cerrados, para `aggregate` o, agrupadas, para `annotate`: la pestaña
    de cerrados y los paneles de indicadores cuentan igual."""
    return {
        "classified": Count("pk", filter=Q(status__in=CLASSIFIED_STATUSES)),
        "discarded": Count("pk", filter=Q(status=DISCARDED)),
        "g1_kg": Sum("classification__g1_kg"),
        "g2_kg": Sum("classification__g2_kg"),
        "partial_discard_kg": Sum("classification__discard_kg"),
        "whole_discard_kg": Sum("drying__dry_weight_kg", filter=Q(status=DISCARDED)),
    }


def closed_kg(totals: dict) -> dict:
    """Los kilos de unas sumas de `closed_totals`. Lo que quedó fuera es el descarte de las
    clasificaciones más el peso seco de los lotes descartados completos."""
    zero = Decimal("0")
    return {
        "g1_kg": totals["g1_kg"] or zero,
        "g2_kg": totals["g2_kg"] or zero,
        "discarded_kg": (totals["partial_discard_kg"] or zero)
        + (totals["whole_discard_kg"] or zero),
    }


def closed_summary(actor, filters: dict) -> dict:
    """Lo que dejó el periodo de cierre: cuántos lotes se clasificaron o se descartaron, los kilos
    de G1 y G2, y los que quedaron fuera. Con los filtros de finca y búsqueda de la lista."""
    totals = (
        closed_in_period(filter_lots(actor, filters), filters)
        .order_by()
        .aggregate(**closed_totals())
    )
    return {
        "classified": totals["classified"],
        "discarded": totals["discarded"],
        **closed_kg(totals),
    }


def get_quality_lot(actor, lot_id):
    lot = visible_lots(actor).filter(pk=lot_id).first()
    if lot is None:
        raise QualityLotNotFound()
    return lot


def lock_lot(actor, lot_id):
    """El lote, en cualquier estado, con la finca de su parcela bloqueada hasta el final de la
    transacción. Quien llama decide si el estado le sirve: uno que no lo es responde su estado,
    no 404."""
    lock_aggregate_root(
        Lot,
        lot_id,
        root="harvest__plot__farm",
        scope=owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"]),
        not_found=QualityLotNotFound,
    )
    return Lot.objects.select_related("harvest__plot__farm", "drying", "quality_evaluation").get(
        pk=lot_id
    )
