from django.db.models import QuerySet

from apps.common.locks import lock_plot_of_producer

from ..exceptions import PlotNotFound
from ..models import Plot


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
    de la transacción, la finca primero (ver `apps/common/locks.py`)."""
    return lock_plot_of_producer(
        Plot, producer_id=actor.producer_id, plot_id=plot_id, not_found=PlotNotFound
    )
