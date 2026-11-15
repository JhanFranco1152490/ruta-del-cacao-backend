"""Las existencias de los paneles de indicadores: lo que hay hoy, sin periodo."""

from django.db.models import Sum

from apps.common.contracts.indicators import FarmGradeKg

from .models import StockBalance

FARM = "warehouse__farm_id"


def stock_by_farm(farm_ids) -> list[FarmGradeKg]:
    rows = (
        StockBalance.objects.filter(**{f"{FARM}__in": farm_ids}, quantity_kg__gt=0)
        .values(FARM, "grade")
        .annotate(kg=Sum("quantity_kg"))
        .order_by()
    )
    return [FarmGradeKg(farm_id=row[FARM], grade=row["grade"], kg=row["kg"]) for row in rows]
