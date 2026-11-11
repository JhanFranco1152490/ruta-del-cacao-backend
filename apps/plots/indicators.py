"""Las parcelas de los paneles de indicadores, con el área declarada para los kg por hectárea."""

from apps.common.codes import format_code
from apps.common.contracts.indicators import PlotArea

from .models import Plot


def plot_areas(farm_ids) -> list[PlotArea]:
    rows = Plot.objects.filter(farm_id__in=farm_ids).values(
        "id", "farm_id", "number", "name", "area_hectares", "is_active"
    )
    return [
        PlotArea(
            plot_id=row["id"],
            farm_id=row["farm_id"],
            code=format_code("P", row["number"]),
            name=row["name"] or "",
            area_hectares=row["area_hectares"],
            is_active=row["is_active"],
        )
        for row in rows
    ]
