from django.db.models import Count, QuerySet

from ..models import Farm
from .farms import scoped_farms


def municipality_counts(actor, **filters) -> list[dict]:
    """Cuántas fincas hay en cada municipio con al menos una, dentro del alcance de `actor`."""
    return list(
        scoped_farms(actor, **filters)
        .values("municipality_code")
        .annotate(farm_count=Count("id"))
        .order_by("municipality_code")
    )


def municipality_points(actor, **filters) -> QuerySet[Farm]:
    """Las fincas de un municipio con lo justo para dibujarlas. Trae el productor en la misma
    consulta para que su nombre no cueste una consulta por finca."""
    return (
        scoped_farms(actor, **filters).select_related("producer").order_by("name_normalized", "id")
    )
