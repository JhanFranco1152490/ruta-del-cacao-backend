"""Las parcelas en los reportes del productor."""

from apps.common.codes import format_code
from apps.common.contracts.reports import ScopedPlot

from .models import Plot


def plot_in_scope(farm_ids, plot_id) -> ScopedPlot | None:
    """La parcela, si es de una de esas fincas; si no existe o es de otra, `None`."""
    row = (
        Plot.objects.filter(pk=plot_id, farm_id__in=farm_ids)
        .values("id", "farm_id", "number", "name")
        .first()
    )
    if row is None:
        return None
    return ScopedPlot(
        plot_id=row["id"],
        farm_id=row["farm_id"],
        code=format_code("P", row["number"]),
        name=row["name"] or "",
    )
