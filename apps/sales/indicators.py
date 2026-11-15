"""Las ventas de los paneles de indicadores: los kilos de las registradas, sin las anuladas."""

from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth

from apps.common.contracts.indicators import FarmMonthSales, IndicatorPeriod

from .models import Grade, Sale


def _kg_of(grade: str) -> Sum:
    return Sum("lines__quantity_kg", filter=Q(lines__grade=grade))


def sales_by_farm(farm_ids, period: IndicatorPeriod) -> list[FarmMonthSales]:
    rows = (
        Sale.objects.filter(
            farm_id__in=farm_ids,
            voided_at__isnull=True,
            sale_date__range=(period.date_from, period.date_to),
        )
        .annotate(month=TruncMonth("sale_date"))
        .values("farm_id", "month")
        # Las líneas multiplican las filas de la venta: se cuenta cada venta una vez.
        .annotate(g1_kg=_kg_of(Grade.G1), g2_kg=_kg_of(Grade.G2), sales=Count("pk", distinct=True))
        .order_by()
    )
    zero = Decimal("0")
    return [
        FarmMonthSales(
            farm_id=row["farm_id"],
            month=IndicatorPeriod.month_key(row["month"]),
            g1_kg=row["g1_kg"] or zero,
            g2_kg=row["g2_kg"] or zero,
            sales=row["sales"],
        )
        for row in rows
    ]
