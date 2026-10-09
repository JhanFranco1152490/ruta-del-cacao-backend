from django.contrib.postgres.lookups import Unaccent
from django.db.models import Count, Q, QuerySet
from django.db.models.functions import Lower

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import PlotNotFound
from ..models import Plot

# La ficha de la parcela es de otra app: se alcanza por su relación con la parcela
# (`characterization`), sin importar su código, como fincas suma el área de sus parcelas por
# `plots`. Es una relación uno a uno, así que el cruce no repite parcelas.
CHARACTERIZED = Q(characterization__isnull=False)
CHARACTERIZATION_FILTERS = {
    "done": CHARACTERIZED,
    "pending": Q(characterization__isnull=True),
}


def _by_name(field: str):
    # Sin tildes ni mayúsculas, como la búsqueda: "Álvarez" va antes que "Zapata" sin importar la
    # intercalación de la base de datos. Fincas y parcelas ya guardan su nombre normalizado.
    return Lower(Unaccent(field))


# Los órdenes de la lista. Cada nivel desempata por su id: con nombres repetidos el orden sigue
# siendo el mismo en cada consulta, y ninguna parcela salta de una página a otra.
PLOT_ORDERINGS = {
    "code": ("code_normalized", "id"),
    # Para agrupar por productor y luego por finca: la lista se pagina por parcela, así que los
    # grupos solo salen completos si el servidor ya las entrega en ese orden.
    "producer,farm,code": (
        _by_name("farm__producer__last_name"),
        _by_name("farm__producer__first_name"),
        "farm__producer_id",
        "farm__name_normalized",
        "farm_id",
        "code_normalized",
        "id",
    ),
}


def list_plots(
    actor,
    farm_id=None,
    producer_id=None,
    is_active: bool | None = None,
    search: str | None = None,
    ordering: str = "code",
) -> QuerySet[Plot]:
    """Las parcelas de las fincas del productor de la sesión. Una finca o un productor ajenos
    no dan error: simplemente no tienen parcelas que mostrar."""
    plots = (
        Plot.objects.filter(**owner_filter(actor, "farm__producer_id"))
        .select_related("farm__producer")
        .order_by(*PLOT_ORDERINGS[ordering])
    )
    if farm_id is not None:
        plots = plots.filter(farm_id=farm_id)
    if producer_id is not None:
        plots = plots.filter(farm__producer_id=producer_id)
    if is_active is not None:
        plots = plots.filter(is_active=is_active)
    term = (search or "").strip()
    if term:
        plots = plots.filter(code__unaccent__icontains=term)
    return plots


def with_characterization(plots: QuerySet[Plot], characterization: str | None) -> QuerySet[Plot]:
    """Solo las que tienen ficha (`done`) o las que no (`pending`); todas sin filtro."""
    if characterization is None:
        return plots
    return plots.filter(CHARACTERIZATION_FILTERS[characterization])


def count_characterizations(plots: QuerySet[Plot]) -> dict:
    """Cuántas de estas parcelas tienen ficha y cuántas no, en una sola consulta."""
    counts = plots.aggregate(total=Count("pk"), done=Count("pk", filter=CHARACTERIZED))
    return {"done": counts["done"], "pending": counts["total"] - counts["done"]}


def get_plot(actor, plot_id) -> Plot:
    try:
        return Plot.objects.select_related("farm__producer").get(
            pk=plot_id, **owner_filter(actor, "farm__producer_id")
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
        scope=owner_filter(actor, "farm__producer_id"),
        not_found=PlotNotFound,
    )
    plot.farm = farm
    return plot
