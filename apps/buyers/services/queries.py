from django.db.models import QuerySet

from apps.common.ownership import owner_filter

from ..exceptions import BuyerNotFound
from ..models import Buyer
from ..usage import used_expression


def readable_buyers(actor) -> QuerySet[Buyer]:
    """Los compradores que `actor` alcanza: todo el directorio de su productor, trabaje en las
    fincas que trabaje. Un comprador le compra al productor, no a una finca."""
    return (
        Buyer.objects.filter(**owner_filter(actor))
        .select_related("producer")
        .annotate(has_records=used_expression())
    )


def list_buyers(actor, *, producer=None) -> QuerySet[Buyer]:
    buyers = readable_buyers(actor)
    # Solo la cuenta técnica elige de qué productor ver: para las demás el alcance ya es el suyo.
    if producer is not None and actor.is_superuser:
        buyers = buyers.filter(producer_id=producer)
    return buyers


def get_buyer(actor, buyer_id) -> Buyer:
    try:
        return readable_buyers(actor).get(pk=buyer_id)
    except Buyer.DoesNotExist:
        raise BuyerNotFound() from None
