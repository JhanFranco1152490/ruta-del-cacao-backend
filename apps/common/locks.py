"""Bloqueos de filas que comparten las apps de la finca y sus parcelas.

Siempre la finca antes que la parcela: dos operaciones que toman los mismos bloqueos en orden
distinto pueden quedar esperándose una a la otra. Un solo lugar impone ese orden, para que una app
nueva que trabaje sobre una parcela (cultivos, cosecha) no tenga que acordarse de él.
"""

from .exceptions import ApiError


def lock_farm_row(farm_model, *, producer_id, farm_id):
    """La finca del productor, bloqueada hasta el final de la transacción, o `None` si no existe o
    es de otro productor."""
    return (
        farm_model.objects.select_for_update().filter(pk=farm_id, producer_id=producer_id).first()
    )


def lock_plot_of_producer(plot_model, *, producer_id, plot_id, not_found: type[ApiError]):
    """La parcela del productor, con su finca y ella misma bloqueadas hasta el final de la
    transacción (primero la finca). Responde `not_found` si no existe o es de otro productor:
    distinguirlas confirmaría que existe.

    El modelo de la finca se toma de la relación de la parcela y no de su app: ninguna app importa
    de otra.
    """
    farm_model = plot_model._meta.get_field("farm").related_model
    farm_id = (
        plot_model.objects.filter(pk=plot_id, farm__producer_id=producer_id)
        .values_list("farm_id", flat=True)
        .first()
    )
    if farm_id is None:
        raise not_found()
    farm = lock_farm_row(farm_model, producer_id=producer_id, farm_id=farm_id)
    # Otra operación pudo eliminar la parcela, o su finca, mientras se esperaba el bloqueo.
    plot = plot_model.objects.select_for_update().filter(pk=plot_id).first() if farm else None
    if plot is None:
        raise not_found()
    plot.farm = farm
    return plot
