from django.db.models import QuerySet

from apps.common.ownership import owner_filter

from ..exceptions import InputNotFound
from ..models import AgriculturalInput
from ..usage import used_expression


def readable_inputs(actor) -> QuerySet[AgriculturalInput]:
    return (
        AgriculturalInput.objects.filter(**owner_filter(actor))
        .select_related("producer")
        .annotate(has_records=used_expression())
    )


def list_inputs(actor, *, producer=None) -> QuerySet[AgriculturalInput]:
    inputs = readable_inputs(actor)
    # Solo la cuenta técnica elige de qué productor ver: para las demás el alcance ya es el suyo.
    if producer is not None and actor.is_superuser:
        inputs = inputs.filter(producer_id=producer)
    return inputs.order_by("name_normalized", "id")


def get_input(actor, input_id) -> AgriculturalInput:
    try:
        return readable_inputs(actor).get(pk=input_id)
    except AgriculturalInput.DoesNotExist:
        raise InputNotFound() from None
