from django.db.models import QuerySet

from apps.common.ownership import owner_filter

from ..exceptions import FacilityNotFound
from ..models import PostharvestFacility
from ..usage import used_expression


def readable_facilities(actor) -> QuerySet[PostharvestFacility]:
    """Los cajones y marquesinas que `actor` alcanza: el Productor, los de todas sus fincas; un
    empleado, los de las fincas en las que trabaja."""
    return (
        PostharvestFacility.objects.filter(
            **owner_filter(actor, "farm__producer_id", farm="farm_id")
        )
        .select_related("farm")
        .annotate(has_records=used_expression())
    )


def list_facilities(actor, *, producer=None) -> QuerySet[PostharvestFacility]:
    """Todos los elementos que `actor` alcanza, activos e inactivos. La finca y los filtros se
    eligen en el dispositivo, que guarda la lista completa para consultarla sin conexión."""
    facilities = readable_facilities(actor)
    # Solo la cuenta técnica elige de qué productor ver: para las demás el alcance ya es el suyo.
    if producer is not None and actor.is_superuser:
        facilities = facilities.filter(farm__producer_id=producer)
    return facilities.order_by("facility_type", "name_normalized", "id")


def get_facility(actor, facility_id) -> PostharvestFacility:
    try:
        return readable_facilities(actor).get(pk=facility_id)
    except PostharvestFacility.DoesNotExist:
        raise FacilityNotFound() from None
