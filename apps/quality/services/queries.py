"""Qué lotes de calidad alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un empleado
lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from datetime import datetime, time
from decimal import Decimal

from django.db.models import Count, Q, QuerySet, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

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
QUALITY_STATUSES = (DRIED, EVALUATED, CLASSIFIED, DISCARDED)

TO_EVALUATE = "to_evaluate"
VIEWS = {
    TO_EVALUATE: (DRIED,),
    "evaluated": (EVALUATED,),
    "closed": (CLASSIFIED, DISCARDED),
}

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


def list_quality_lots(actor, filters: dict) -> QuerySet:
    """Los lotes de una vista: por evaluar, del que se secó primero; evaluados, del que se evaluó
    primero; cerrados, del que se clasificó o descartó más recientemente."""
    view = filters.get("view", TO_EVALUATE)
    lots = filter_lots(actor, filters).filter(status__in=VIEWS[view])
    if view == TO_EVALUATE:
        return lots.order_by("drying__ended_at", "code")
    if view == "evaluated":
        return lots.order_by("quality_evaluation__evaluated_at", "code")
    closed_at = Coalesce("classification__classified_at", "discard__discarded_at")
    return lots.order_by(closed_at.desc(), "code")


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


def get_quality_lot(actor, lot_id):
    lot = visible_lots(actor).filter(pk=lot_id).first()
    if lot is None:
        raise QualityLotNotFound()
    return lot
