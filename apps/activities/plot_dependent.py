from apps.common.plot_dependents import PlotDependent

from .choices import ActivityStatus
from .models import AgriculturalActivity
from .services.delete import remove_activity


def _activities_of(plot):
    return AgriculturalActivity.objects.filter(plot_id=plot.pk).order_by("scheduled_date", "id")


def _important_record(plot) -> str | None:
    # Una labor realizada es un registro de campo: la parcela se desactiva en lugar de eliminarse.
    # Lo que no se llegó a hacer, vencido o no, se va con la parcela creada por error.
    if _activities_of(plot).filter(status=ActivityStatus.DONE).exists():
        return f"La parcela «{plot.code}» tiene actividades realizadas."
    return None


def _delete_all(plot, actor) -> None:
    # Quien llama ya tiene bloqueada la finca, raíz de la parcela y de sus actividades.
    for activity in _activities_of(plot):
        remove_activity(activity, actor)


activities_dependent = PlotDependent(
    name="activities",
    important_record=_important_record,
    count=lambda plot: _activities_of(plot).count(),
    delete_all=_delete_all,
    models=(AgriculturalActivity,),
)
