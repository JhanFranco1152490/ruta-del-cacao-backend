from ..exceptions import PlotNotFound
from ..models import PlotCharacterization

# Los modelos de la parcela y de la finca se toman de las relaciones y no de sus apps: ninguna
# app importa de otra.
Plot = PlotCharacterization._meta.get_field("plot").related_model
Farm = Plot._meta.get_field("farm").related_model


def lock_plot(actor, plot_id):
    """La parcela del productor de la sesión, con su finca y ella misma bloqueadas hasta el final
    de la transacción.

    Siempre la finca antes que la parcela, en el mismo orden que usan todas las operaciones de
    parcelas: dos operaciones que toman los mismos bloqueos en orden distinto pueden quedar
    esperándose una a la otra.
    """
    farm_id = (
        Plot.objects.filter(pk=plot_id, farm__producer_id=actor.producer_id)
        .values_list("farm_id", flat=True)
        .first()
    )
    if farm_id is None:
        raise PlotNotFound()
    farm = Farm.objects.select_for_update().filter(pk=farm_id).first()
    # Otra operación pudo eliminar la parcela, o su finca, mientras se esperaba el bloqueo.
    plot = Plot.objects.select_for_update().filter(pk=plot_id).first() if farm else None
    if plot is None:
        raise PlotNotFound()
    plot.farm = farm
    return plot
