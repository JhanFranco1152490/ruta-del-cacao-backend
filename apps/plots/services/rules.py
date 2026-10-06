"""Reglas de una parcela que dependen de las demás parcelas de su finca.

Todas corren con la fila de la finca bloqueada (`lock_farm`). Las altas, las ediciones y las
reactivaciones de parcelas, y los cambios de área de la finca, bloquean esa misma fila, así que
dos de ellas nunca evalúan las reglas a la vez con datos que la otra está por cambiar: dos
parcelas registradas sin conexión en dos teléfonos se revisan una después de la otra.
"""

from decimal import Decimal

from django.db.models import Sum

from apps.common.ownership import owner_filter

from ..exceptions import (
    FarmInactive,
    FarmNotFound,
    PlotAreaExceedsFarm,
    PlotOverlap,
    PlotTooFarFromFarm,
)
from ..geometry import (
    Boundary,
    find_overlaps,
    max_distance_from_farm_m,
    measured_area_hectares,
    suggest_boundary,
    to_polygon,
    vertices_too_far_from,
)
from ..models import Plot

# El modelo de la finca se toma de la relación y no de su app: ninguna app importa de otra.
Farm = Plot._meta.get_field("farm").related_model


def lock_farm(actor, farm_id):
    """La finca del productor de la sesión, bloqueada hasta el final de la transacción."""
    farm = Farm.objects.select_for_update().filter(pk=farm_id, **owner_filter(actor)).first()
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


def check_within_farm_reach(farm, boundary: Boundary) -> None:
    """Ningún vértice puede quedar más lejos del punto de la finca de lo que cabe en una finca de
    ese tamaño."""
    far = vertices_too_far_from(
        boundary.vertices, (farm.latitude, farm.longitude), farm.area_hectares
    )
    if far:
        position, metres = far[0]
        raise PlotTooFarFromFarm(position, metres, max_distance_from_farm_m(farm.area_hectares))


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
