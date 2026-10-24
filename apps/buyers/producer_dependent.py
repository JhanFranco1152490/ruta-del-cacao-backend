from apps.common.contracts.producer_dependents import ProducerDependent

from .models import Buyer
from .services import remove_buyer
from .usage import is_used


def _buyers_of(producer):
    return Buyer.objects.filter(producer_id=producer.pk).order_by("id")


def _important_record(producer) -> str | None:
    # La misma regla que eliminar un comprador por separado: uno que algún registro usa es
    # importante. Sin su nombre: el comprador puede ser una persona natural.
    if any(is_used(buyer) for buyer in _buyers_of(producer)):
        return "Un comprador del productor tiene ventas registradas."
    return None


def _delete_all(producer, actor) -> None:
    for buyer in _buyers_of(producer).select_for_update():
        remove_buyer(buyer, actor)


buyers_dependent = ProducerDependent(
    name="buyers",
    important_record=_important_record,
    count=lambda producer: _buyers_of(producer).count(),
    delete_all=_delete_all,
    models=(Buyer,),
)
