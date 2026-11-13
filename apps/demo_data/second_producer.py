"""Villa Rosa, de otro productor de demostración: una cosecha que pasó por fermentación, secado y
calidad, entró a bodega y se vendió en parte, y otra reciente que aún no se seca.

Sin esto, el panel de la asociación tendría una sola finca con cifras, y no se vería que el
productor de demostración solo alcanza lo suyo. Lo registra la cuenta Productor de Villa Rosa con
los servicios de cada app, como el capataz y la encargada de calidad en La Esperanza; esa cuenta no
entra a la aplicación (no tiene contraseña) y no aparece en el menú de cuentas de demostración.
Se crea una sola vez: si la finca ya tiene alguna cosecha, no se toca.
"""

from decimal import Decimal

from apps.accounts.models import User
from apps.accounts.system_roles import PRODUCER
from apps.buyers.models import Buyer
from apps.buyers.services import create_buyer
from apps.facilities.models import PostharvestFacility
from apps.facilities.services.create import create_facility
from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.plots.models import Plot
from apps.sales.services import create_sale
from apps.warehouse.services.warehouses import create_warehouse

from .catalog import SECOND_BUYER, SECOND_FACILITIES, SECOND_FARM, SECOND_PLOT
from .postharvest import harvested_lot
from .sales import _line, _sale_data
from .warehouse import WAREHOUSE_NAME, _stored_lot

FRESH_HARVEST_KG = Decimal("180")


def seed_second_producer() -> list[str]:
    farm = Farm.objects.filter(name=SECOND_FARM).select_related("producer").first()
    if farm is None or Harvest.objects.filter(plot__farm=farm).exists():
        return []
    owner = User.objects.get(producer=farm.producer, groups__role__code=PRODUCER)
    plot = Plot.objects.get(farm=farm, name=SECOND_PLOT)
    for definition in SECOND_FACILITIES:
        if not PostharvestFacility.objects.filter(farm=farm, name__iexact=definition["name"]):
            create_facility(owner, {**definition, "farm_id": farm.pk})
    warehouse = create_warehouse(owner, {"farm_id": farm.pk, "name": WAREHOUSE_NAME})
    # El mismo productor recolecta, evalúa e ingresa: no tiene empleados.
    stored = _stored_lot(
        owner, owner, owner, plot, warehouse, harvest_days_ago=24, grades=("90.0", "24.0")
    )
    if stored is None:
        return []
    fresh = harvested_lot(owner, owner, plot, days_ago=2, weight=FRESH_HARVEST_KG)
    create_sale(owner, _sale_data(farm, _buyer(owner), [_line(stored, "g1", "60.0", 18000)]))
    return [
        f"{SECOND_FARM}: {stored.code} en bodega y vendido en parte, y {fresh.code} por fermentar"
    ]


def _buyer(owner: User) -> Buyer:
    existing = Buyer.objects.filter(
        producer=owner.producer,
        document_type=SECOND_BUYER["document_type"],
        identity_document=SECOND_BUYER["identity_document"],
    ).first()
    return existing or create_buyer(owner, SECOND_BUYER)
