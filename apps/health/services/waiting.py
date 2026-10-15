from django.db.models import QuerySet

from apps.common.ownership import owner_filter

from ..models import Detection


def detections_without_control(actor, producer_id=None) -> QuerySet[Detection]:
    """Las detecciones que no tienen ningún control, del monitoreo más antiguo al más reciente, en
    las fincas que alcanza `actor`. Quien solo registra lo suyo deja una plaga con "Ninguno por
    ahora", y quien programa controles tiene que enterarse. Sin fecha mínima: una detección vieja
    sin atender no debe perderse. `producer_id` solo lo usa la cuenta técnica."""
    detections = Detection.objects.filter(
        treatments__isnull=True,
        **owner_filter(
            actor,
            "monitoring__activity__plot__farm__producer_id",
            farm="monitoring__activity__plot__farm_id",
        ),
    )
    if actor.is_superuser and producer_id is not None:
        detections = detections.filter(monitoring__activity__plot__farm__producer_id=producer_id)
    return detections.select_related("pest_disease", "monitoring__activity__plot__farm").order_by(
        "monitoring__activity__done_date", "id"
    )
