"""Reglas de una parcela que dependen de las demás parcelas de su finca.

Todas corren con la fila de la finca bloqueada (`lock_farm`). Las altas, las ediciones y las
reactivaciones de parcelas, y los cambios de área de la finca, bloquean esa misma fila, así que
dos de ellas nunca evalúan las reglas a la vez con datos que la otra está por cambiar: dos
parcelas registradas sin conexión en dos teléfonos se revisan una después de la otra.
"""

from decimal import Decimal

from django.db.models import Sum

from ..exceptions import FarmInactive, FarmNotFound, PlotAreaExceedsFarm, PlotOverlap
from ..geometry import (
    Boundary,
    find_overlaps,
    measured_area_hectares,
    suggest_boundary,
    to_polygon,
)
from ..models import Plot

# El modelo de la finca se toma de la relación y no de su app: ninguna app importa de otra.
Farm = Plot._meta.get_field("farm").related_model


def lock_farm(actor, farm_id):
    """La finca del productor de la sesión, bloqueada hasta el final de la transacción."""
    farm = (
        Farm.objects.select_for_update().filter(pk=farm_id, producer_id=actor.producer_id).first()
    )
    if farm is None:
        raise FarmNotFound()
    return farm


def ensure_farm_active(farm) -> None:
    if not farm.is_active:
        raise FarmInactive()


def check_available_area(farm, area_hectares: Decimal, exclude_plot_id=None) -> None:
    """La suma de las áreas declaradas de las parcelas activas no puede superar la de la finca.
    `exclude_plot_id` deja fuera a la parcela que se edita, para no contar su área anterior."""
    totals = _active_plots(farm, exclude_plot_id).aggregate(allocated=Sum("area_hectares"))
    allocated = totals["allocated"] or Decimal("0")
    if allocated + area_hectares > farm.area_hectares:
        raise PlotAreaExceedsFarm()


def check_no_overlap(farm, boundary: Boundary, exclude_plot_id=None) -> None:
    """El contorno no puede invadir el de otra parcela activa de la misma finca."""
    neighbours = {
        plot: to_polygon(plot.boundary)
        for plot in _active_plots(farm, exclude_plot_id)
        .filter(boundary__isnull=False)
        .order_by("code_normalized")
    }
    overlaps = find_overlaps(boundary.polygon, neighbours)
    if not overlaps:
        return

    suggestion = suggest_boundary(boundary, [neighbours[overlap.key] for overlap in overlaps])
    raise PlotOverlap(
        overlaps=[(overlap.key, overlap.area_hectares) for overlap in overlaps],
        suggested_boundary=suggestion,
        suggested_measured_area_hectares=(
            None if suggestion is None else measured_area_hectares(to_polygon(suggestion))
        ),
    )


def _active_plots(farm, exclude_plot_id):
    plots = Plot.objects.filter(farm=farm, is_active=True)
    if exclude_plot_id is not None:
        plots = plots.exclude(pk=exclude_plot_id)
    return plots
