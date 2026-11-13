"""Los kg secos de los paneles de indicadores."""

from django.db.models import Sum
from django.db.models.functions import TruncMonth

from apps.common.contracts.indicators import IndicatorPeriod, PlotMonthDried

from .models import DryingProcess

HARVEST = "lot__harvest"


def dried(farm_ids, period: IndicatorPeriod) -> list[PlotMonthDried]:
    """Los secados terminados, en el mes de su cosecha: así el seco de una parcela habla de las
    mismas cosechas que su kg en baba, aunque el secado termine en otro mes o fuera del periodo."""
    rows = (
        DryingProcess.objects.filter(
            ended_at__isnull=False,
            **{
                f"{HARVEST}__plot__farm_id__in": farm_ids,
                f"{HARVEST}__harvest_date__range": (period.date_from, period.date_to),
            },
        )
        .annotate(month=TruncMonth(f"{HARVEST}__harvest_date"))
        .values(f"{HARVEST}__plot_id", f"{HARVEST}__plot__farm_id", "month")
        .annotate(dry_kg=Sum("dry_weight_kg"), green_kg=Sum(f"{HARVEST}__green_weight_kg"))
        .order_by()
    )
    return [
        PlotMonthDried(
            plot_id=row[f"{HARVEST}__plot_id"],
            farm_id=row[f"{HARVEST}__plot__farm_id"],
            month=IndicatorPeriod.month_key(row["month"]),
            dry_kg=row["dry_kg"],
            green_kg=row["green_kg"],
        )
        for row in rows
    ]
