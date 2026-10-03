from django.db.models import QuerySet

from ..exceptions import PlotNotFound
from ..models import Plot
from . import rules


def list_plots(
    actor, farm_id=None, is_active: bool | None = None, search: str | None = None
) -> QuerySet[Plot]:
    """Las parcelas de las fincas del productor de la sesión. Una finca ajena en `farm_id` no
    da error: simplemente no tiene parcelas que mostrar."""
    plots = (
        Plot.objects.filter(farm__producer_id=actor.producer_id)
        .select_related("farm")
        .order_by("code_normalized", "id")
    )
    if farm_id is not None:
        plots = plots.filter(farm_id=farm_id)
    if is_active is not None:
        plots = plots.filter(is_active=is_active)
    term = (search or "").strip()
    if term:
        plots = plots.filter(code__unaccent__icontains=term)
    return plots


def get_plot(actor, plot_id) -> Plot:
    try:
        return Plot.objects.select_related("farm").get(
            pk=plot_id, farm__producer_id=actor.producer_id
        )
    except Plot.DoesNotExist:
        raise PlotNotFound() from None


def lock_plot(actor, plot_id) -> Plot:
    """La parcela del productor de la sesión, con su finca y ella misma bloqueadas hasta el final
    de la transacción.

    Siempre la finca antes que la parcela, en el mismo orden que el alta: dos operaciones que
    toman los mismos bloqueos en orden distinto pueden quedar esperándose una a la otra.
    """
    farm_id = (
        Plot.objects.filter(pk=plot_id, farm__producer_id=actor.producer_id)
        .values_list("farm_id", flat=True)
        .first()
    )
    if farm_id is None:
        raise PlotNotFound()
    farm = rules.lock_farm(actor, farm_id)
    # Otra operación pudo eliminarla mientras se esperaba el bloqueo de la finca.
    plot = Plot.objects.select_for_update().filter(pk=plot_id).first()
    if plot is None:
        raise PlotNotFound()
    plot.farm = farm
    return plot
