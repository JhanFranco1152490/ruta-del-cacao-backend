from django.db import transaction

from ..exceptions import LotNotClassified, LotQrAlreadyExists
from ..models import LotQrCode
from ..qr_rules import can_have_qr, new_qr_token
from . import queries


@transaction.atomic
def generate_lot_qr(actor, lot_id) -> LotQrCode:
    """Genera el código QR del lote, si `actor` lo alcanza y el lote está clasificado. Uno por
    lote: con la finca bloqueada, dos pedidos a la vez se atienden uno tras otro y el segundo
    encuentra el primero."""
    lot = queries.lock_lot(actor, lot_id)
    if not can_have_qr(lot.status):
        raise LotNotClassified(lot.status)
    if LotQrCode.objects.filter(lot=lot).exists():
        raise LotQrAlreadyExists()
    return LotQrCode.objects.create(lot=lot, token=new_qr_token(), created_by=actor)
