"""Qué cosechas y parcelas alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un
empleado lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from django.db.models import QuerySet

from apps.common.contracts.assignable import person_options
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import HarvestNotFound, InvalidHarvest, PlotNotFound
from ..models import Harvest
from .rules import ADD_PERMISSION

# El modelo de la parcela se toma de la relación y no de su app: ninguna app importa de otra.
Plot = Harvest._meta.get_field("plot").related_model


def visible_harvests(actor) -> QuerySet[Harvest]:
    # El lote es de otra app: se alcanza por la relación inversa, sin importarla.
    return Harvest.objects.filter(
        **owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id")
    ).select_related("plot__farm", "variety", "collector", "registered_by", "lot")


def list_harvests(
    actor, date_from, date_to, farm_id=None, plot_id=None, producer_id=None
) -> QuerySet[Harvest]:
    """Las cosechas recogidas entre las dos fechas, ambas incluidas, de la más reciente a la más
    antigua. Una finca o una parcela ajenas no dan error: simplemente no tienen cosechas que
    mostrar. `producer_id` solo lo usa la cuenta técnica, que sin él ve las de todos."""
    harvests = visible_harvests(actor).filter(harvest_date__range=(date_from, date_to))
    if farm_id is not None:
        harvests = harvests.filter(plot__farm_id=farm_id)
    if plot_id is not None:
        harvests = harvests.filter(plot_id=plot_id)
    if actor.is_superuser and producer_id is not None:
        harvests = harvests.filter(plot__farm__producer_id=producer_id)
    return harvests.order_by("-harvest_date", "-created_at", "id")


def collector_options(actor, producer_id=None) -> list[dict]:
    """Las cuentas a las que `actor` puede nombrar recolectoras; ver `person_options`."""
    return person_options(
        actor,
        producer_id,
        ADD_PERMISSION,
        producer_required=lambda: InvalidHarvest(
            "producer", "Indica de qué productor son los recolectores."
        ),
    )


def get_harvest(actor, harvest_id) -> Harvest:
    harvest = visible_harvests(actor).filter(pk=harvest_id).first()
    if harvest is None:
        raise HarvestNotFound()
    return harvest


def lock_plot(actor, plot_id):
    """La parcela, con su finca bloqueada hasta el final de la transacción. Solo la finca: es la
    raíz de todo lo que cuelga de ella (ver `apps/common/locks.py`)."""
    plot, farm = lock_aggregate_root(
        Plot,
        plot_id,
        root="farm",
        scope=owner_filter(actor, "farm__producer_id", farm="farm_id"),
        not_found=PlotNotFound,
    )
    plot.farm = farm
    return plot


def lock_harvest(actor, harvest_id) -> Harvest:
    """La cosecha, con la finca de su parcela bloqueada hasta el final de la transacción."""
    harvest, farm = lock_aggregate_root(
        Harvest,
        harvest_id,
        root="plot__farm",
        scope=owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id"),
        not_found=HarvestNotFound,
    )
    harvest.plot = Plot.objects.get(pk=harvest.plot_id)
    harvest.plot.farm = farm
    return harvest
