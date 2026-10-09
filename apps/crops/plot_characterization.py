from django.db.models import Exists

from .models import PlotCharacterization


def plot_is_characterized(plot_ref) -> Exists:
    """Si la parcela de la consulta de afuera tiene ficha: lo que la lista de parcelas filtra y
    cuenta sin importar este modelo."""
    return Exists(PlotCharacterization.objects.filter(plot_id=plot_ref))
