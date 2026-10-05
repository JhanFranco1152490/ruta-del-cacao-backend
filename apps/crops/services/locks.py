from apps.common.locks import lock_aggregate_root

from ..exceptions import PlotNotFound
from ..models import PlotCharacterization

# Los modelos de la parcela y de la finca se toman de las relaciones y no de sus apps: ninguna
# app importa de otra.
Plot = PlotCharacterization._meta.get_field("plot").related_model


def lock_plot(actor, plot_id):
    """La parcela del productor de la sesión, con su finca bloqueada hasta el final de la
    transacción. Solo la finca, como el resto de las escrituras bajo ella: la ficha de una parcela
    no se guarda a la vez que se edita, desactiva o elimina esa parcela, y no hay un segundo
    bloqueo que pueda esperarse con otro (ver `apps/common/locks.py`)."""
    plot, farm = lock_aggregate_root(
        Plot,
        plot_id,
        root="farm",
        scope={"farm__producer_id": actor.producer_id},
        not_found=PlotNotFound,
    )
    plot.farm = farm
    return plot
