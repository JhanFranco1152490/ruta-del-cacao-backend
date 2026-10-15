"""Qué cosechas y parcelas alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un
empleado lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from django.db.models import QuerySet

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import HarvestNotFound, PlotNotFound
from ..models import Harvest

# El modelo de la parcela se toma de la relación y no de su app: ninguna app importa de otra.
Plot = Harvest._meta.get_field("plot").related_model


def visible_harvests(actor) -> QuerySet[Harvest]:
    return Harvest.objects.filter(
        **owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id")
    ).select_related("plot__farm", "variety", "collector", "registered_by")


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
