from django.db.models import Prefetch, QuerySet

from ..exceptions import CharacterizationNotFound, PlotNotFound
from ..models import PlotCharacterization, PlotCharacterizationVariety
from .locks import Plot


def with_rows(characterizations: QuerySet) -> QuerySet:
    """Las fichas con sus filas y la variedad de cada una, en dos consultas más sin importar
    cuántas sean."""
    rows = PlotCharacterizationVariety.objects.select_related("variety").order_by(
        "variety__name_normalized", "id"
    )
    return characterizations.prefetch_related(Prefetch("varieties", queryset=rows))


def list_characterizations(actor, farm_id) -> QuerySet:
    """Las fichas de las parcelas de una finca del productor de la sesión. Una finca ajena no da
    error: simplemente no tiene fichas que mostrar."""
    characterizations = PlotCharacterization.objects.filter(
        plot__farm_id=farm_id, plot__farm__producer_id=actor.producer_id
    ).order_by("plot__code_normalized", "plot_id")
    return with_rows(characterizations)


def get_characterization(actor, plot_id) -> PlotCharacterization:
    characterization = (
        with_rows(PlotCharacterization.objects.filter(plot__farm__producer_id=actor.producer_id))
        .filter(pk=plot_id)
        .first()
    )
    if characterization is not None:
        return characterization
    # Los dos son 404, pero el mensaje dice cuál de los dos falta.
    if Plot.objects.filter(pk=plot_id, farm__producer_id=actor.producer_id).exists():
        raise CharacterizationNotFound()
    raise PlotNotFound()
