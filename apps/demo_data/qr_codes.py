"""El código QR del lote vendido de La Esperanza, para escanearlo en vivo y mostrar que su página
pública no trae al comprador, los precios ni a nadie aunque el lote tenga ventas. Lo genera el
Productor con el servicio de lotes. El lote clasificado con descarte de la calidad se deja sin QR,
para generarlo en vivo.
"""

from apps.accounts.models import User
from apps.lots.models import Lot, LotQrCode
from apps.lots.services.qr import generate_lot_qr

from .catalog import DEMO_FARM


def seed_lot_qr_codes(owner: User) -> list[str]:
    lot = _sold_lot(owner)
    if lot is None or LotQrCode.objects.filter(lot=lot).exists():
        return []
    generate_lot_qr(owner, lot.pk)
    return [f"Código QR: lote {lot.code}"]


def _sold_lot(owner):
    # Con líneas de venta vigentes: sin la primera condición, `voided_at__isnull` también da los
    # lotes sin ventas.
    return (
        Lot.objects.filter(
            harvest__plot__farm__producer=owner.producer,
            harvest__plot__farm__name=DEMO_FARM,
            sale_lines__isnull=False,
            sale_lines__sale__voided_at__isnull=True,
        )
        .distinct()
        .order_by("code")
        .first()
    )
