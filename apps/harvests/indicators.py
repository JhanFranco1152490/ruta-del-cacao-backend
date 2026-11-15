"""Los kg en baba de los paneles de indicadores."""

from django.db.models import Sum
from django.db.models.functions import TruncMonth

from apps.common.contracts.indicators import IndicatorPeriod, PlotMonthKg, VarietyKg

from .models import Harvest


def harvested(farm_ids, period: IndicatorPeriod) -> list[PlotMonthKg]:
    rows = (
        Harvest.objects.filter(
            plot__farm_id__in=farm_ids,
            harvest_date__range=(period.date_from, period.date_to),
        )
        .annotate(month=TruncMonth("harvest_date"))
        .values("plot_id", "plot__farm_id", "month")
        .annotate(kg=Sum("green_weight_kg"))
        .order_by()
    )
    return [
        PlotMonthKg(
            plot_id=row["plot_id"],
            farm_id=row["plot__farm_id"],
            month=IndicatorPeriod.month_key(row["month"]),
            kg=row["kg"],
        )
        for row in rows
    ]


def harvested_by_variety(farm_ids, period: IndicatorPeriod) -> list[VarietyKg]:
    rows = (
        Harvest.objects.filter(
            plot__farm_id__in=farm_ids,
            harvest_date__range=(period.date_from, period.date_to),
        )
        .values("variety_id", "variety__name")
        .annotate(kg=Sum("green_weight_kg"))
        .order_by()
    )
    return [
        VarietyKg(variety_id=row["variety_id"], name=row["variety__name"], kg=row["kg"])
        for row in rows
    ]
