from apps.common.farm_dependents import FarmDependent

from .models import Plot
from .services.delete import has_business_records, remove_plot


def _plots_of(farm):
    return Plot.objects.filter(farm_id=farm.pk).order_by("code_normalized", "id")


def _important_record(farm) -> str | None:
    # La misma regla que eliminar una parcela por separado: cualquier tabla que la apunte, salvo
    # su auditoría, la vuelve importante.
    for plot in _plots_of(farm):
        if has_business_records(plot):
            return f"La parcela «{plot.code}» tiene registros asociados."
    return None


def _delete_all(farm, actor) -> None:
    for plot in _plots_of(farm).select_for_update():
        remove_plot(plot, actor)


plots_dependent = FarmDependent(
    name="plots",
    important_record=_important_record,
    count=lambda farm: _plots_of(farm).count(),
    delete_all=_delete_all,
    models=(Plot,),
)
