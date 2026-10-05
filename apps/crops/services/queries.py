from django.db.models import Prefetch, QuerySet

from ..exceptions import CharacterizationNotFound, PlotNotFound
from ..models import PlotCharacterization, PlotCharacterizationAuditEvent, PlotPlanting
from .locks import Plot


def with_rows(characterizations: QuerySet) -> QuerySet:
    """Las fichas con sus siembras y la variedad de cada una, en dos consultas más sin importar
    cuántas sean."""
    rows = PlotPlanting.objects.select_related("variety").order_by(
        "variety__name_normalized", "planting_date", "id"
    )
    return characterizations.prefetch_related(Prefetch("plantings", queryset=rows))


def list_characterizations(actor, farm_id) -> QuerySet:
    """Las fichas de las parcelas de una finca del productor de la sesión. Una finca ajena no da
    error: simplemente no tiene fichas que mostrar."""
    characterizations = PlotCharacterization.objects.filter(
        plot__farm_id=farm_id, plot__farm__producer_id=actor.effective_producer_id
    ).order_by("plot__code_normalized", "plot_id")
    return with_rows(characterizations)


def get_characterization(actor, plot_id) -> PlotCharacterization:
    characterization = (
        with_rows(
            PlotCharacterization.objects.filter(
                plot__farm__producer_id=actor.effective_producer_id
            )
        )
        .filter(pk=plot_id)
        .first()
    )
    if characterization is not None:
        return characterization
    # Los dos son 404, pero el mensaje dice cuál de los dos falta.
    if Plot.objects.filter(pk=plot_id, farm__producer_id=actor.effective_producer_id).exists():
        raise CharacterizationNotFound()
    raise PlotNotFound()


def list_history(actor, plot_id) -> QuerySet:
    """Las versiones de la ficha de una parcela del productor de la sesión, de la más nueva a la
    más vieja. Una parcela sin ficha no da error: no tiene versiones que mostrar."""
    if not Plot.objects.filter(pk=plot_id, farm__producer_id=actor.effective_producer_id).exists():
        raise PlotNotFound()
    return (
        PlotCharacterizationAuditEvent.objects.filter(plot_id=plot_id)
        .select_related("actor")
        .order_by("-version", "-occurred_at")
    )
