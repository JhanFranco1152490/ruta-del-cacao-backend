from django.db.models import QuerySet

from apps.common.locks import lock_aggregate_root

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
    """La parcela del productor de la sesión, con su finca bloqueada hasta el final de la
    transacción. Solo la finca: es la raíz de todo lo que cuelga de ella, y bloquear además la
    fila de la parcela no deja correr nada en paralelo (la finca ya lo serializa) y sí abriría la
    puerta a que dos operaciones se esperen entre sí (ver `apps/common/locks.py`)."""
    plot, farm = lock_aggregate_root(
        Plot,
        plot_id,
        root="farm",
        scope={"farm__producer_id": actor.producer_id},
        not_found=PlotNotFound,
    )
    plot.farm = farm
    return plot
