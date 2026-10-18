from apps.common.plot_dependents import PlotDependent

from .models import Harvest


def _harvests_of(plot):
    return Harvest.objects.filter(plot_id=plot.pk)


def _important_record(plot) -> str | None:
    # Una cosecha es un registro de campo y de ella cuelga el lote: la parcela se desactiva en
    # lugar de eliminarse.
    if _harvests_of(plot).exists():
        return f"La parcela «{plot.code}» tiene cosechas registradas."
    return None


def _delete_all(plot, actor) -> None:
    # Nunca hay nada que eliminar: con una cosecha la parcela no llega a borrarse.
    return None


harvests_dependent = PlotDependent(
    name="harvests",
    important_record=_important_record,
    count=lambda plot: _harvests_of(plot).count(),
    delete_all=_delete_all,
    models=(Harvest,),
)
