"""Lo que la bitácora de cambios muestra con la semilla, además de lo que ya dejan las demás partes
(las altas, la evaluación corregida, la salida y la venta anuladas, los roles del capataz):

- el capataz corrige la cosecha de La Esperanza que queda sin lote: el peso y el recolector, que
  sale por su nombre antes y después;
- el productor edita El Mirador: su área y sus detalles;
- el productor cambia el teléfono de un comprador: un dato personal, que dice que cambió sin sus
  valores.

Todo por los servicios de cada app y una sola vez: si el evento ya existe, no se repite.
"""

from decimal import Decimal

from apps.accounts.models import User
from apps.buyers.models import Buyer, BuyerAuditEvent
from apps.buyers.services.update import update_buyer
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.services.farms import update_farm
from apps.harvests.models import Harvest, HarvestAuditEvent
from apps.harvests.services.update import update_harvest

from .catalog import DEMO_FARM

EDITED_FARM = "El Mirador"
EDITED_FARM_DETAILS = (
    "Finca pequeña de renovación con clones regionales; vía destapada en invierno."
)
# Medio kilo más: lo que pesó de verdad al repetir la pesada.
CORRECTED_KILOS = Decimal("0.5")
# El número nuevo del comprador: ficticio, con el formato de un celular.
NEW_PHONE = "3105550123"


def _harvest_correction(owner: User, foreman: User) -> list[str]:
    if HarvestAuditEvent.objects.filter(
        producer_ref=owner.producer_id, action=HarvestAuditEvent.Action.UPDATED
    ).exists():
        return []
    harvest = (
        Harvest.objects.filter(plot__farm__name=DEMO_FARM, plot__farm__producer=owner.producer)
        .filter(lot__isnull=True)
        .order_by("harvest_date")
        .first()
    )
    if harvest is None:
        return []
    collector = owner if harvest.collector_id == foreman.pk else foreman
    update_harvest(
        foreman,
        harvest.pk,
        harvest.version,
        {
            "green_weight_kg": harvest.green_weight_kg + CORRECTED_KILOS,
            "collector_id": collector.pk,
        },
    )
    return ["Bitácora: cosecha corregida por el capataz"]


def _farm_edit(owner: User) -> list[str]:
    farm = Farm.objects.filter(producer=owner.producer, name=EDITED_FARM).first()
    if (
        farm is None
        or FarmAuditEvent.objects.filter(farm=farm, action=FarmAuditEvent.Action.UPDATED).exists()
    ):
        return []
    update_farm(
        owner,
        farm.pk,
        farm.version,
        {"area_hectares": farm.area_hectares + Decimal("0.30"), "details": EDITED_FARM_DETAILS},
    )
    return [f"Bitácora: {EDITED_FARM} editada"]


def _buyer_phone(owner: User) -> list[str]:
    if BuyerAuditEvent.objects.filter(
        producer_ref=owner.producer_id, action=BuyerAuditEvent.Action.UPDATED
    ).exists():
        return []
    buyer = (
        Buyer.objects.filter(producer=owner.producer, is_active=True)
        .exclude(phone=NEW_PHONE)
        .order_by("name")
        .first()
    )
    if buyer is None:
        return []
    update_buyer(owner, buyer.pk, buyer.version, {"phone": NEW_PHONE})
    return ["Bitácora: teléfono de un comprador cambiado"]


def seed_audit_log(owner: User, foreman: User) -> list[str]:
    return [*_harvest_correction(owner, foreman), *_farm_edit(owner), *_buyer_phone(owner)]
