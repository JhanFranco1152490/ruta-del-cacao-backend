from django.db.models import Exists, Sum

from .models import PlotCharacterization, PlotPlanting


def plot_is_characterized(plot_ref) -> Exists:
    """Si la parcela de la consulta de afuera tiene ficha: lo que la lista de parcelas filtra y
    cuenta sin importar este modelo."""
    return Exists(PlotCharacterization.objects.filter(plot_id=plot_ref))


def plot_tree_count(plot_id) -> int | None:
    """La suma de los árboles de todas las siembras de la parcela, o `None` si no tiene ficha o
    la ficha no tiene siembras."""
    return PlotPlanting.objects.filter(characterization_id=plot_id).aggregate(
        total=Sum("tree_count")
    )["total"]
