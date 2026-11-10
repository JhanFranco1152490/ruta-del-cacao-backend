"""Las ventas de La Esperanza: una registrada a Chocolates del Oriente S.A.S. con su soporte y otra
anulada, hechas por el Comercializador con los servicios de ventas, sobre los lotes que deja la
bodega. Se crean una sola vez: si la finca ya tiene ventas, no se tocan. Lo que venden deja
existencias para registrar otra en vivo.
"""

from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.accounts.models import User
from apps.buyers.models import Buyer
from apps.farms.models import Farm
from apps.sales.models import Sale
from apps.sales.services import attach_invoice, create_sale, void_sale
from apps.warehouse.models import StockBalance

from .catalog import DEMO_FARM, DEMO_SALES_MANAGER_EMAIL

# Un PDF mínimo pero válido, para que el soporte se vea en la ficha de la venta.
DEMO_INVOICE = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def seed_sales(owner: User) -> list[str]:
    manager = User.objects.filter(email__iexact=DEMO_SALES_MANAGER_EMAIL).first()
    farm = Farm.objects.filter(producer=owner.producer, name=DEMO_FARM).first()
    if manager is None or farm is None or Sale.objects.filter(farm=farm).exists():
        return []
    registered = _registered_sale(manager, owner, farm)
    voided = _voided_sale(manager, owner, farm)
    return [
        f"Ventas: {sale.code}" + (" anulada" if sale.voided_at else " con su soporte")
        for sale in (registered, voided)
        if sale is not None
    ]


def _registered_sale(manager, owner, farm):
    stock = _richest(farm, "g1", minimum=Decimal("50.0"))
    g2 = StockBalance.objects.filter(lot=stock.lot, grade="g2").first() if stock else None
    buyer = _buyer(owner, "900000001")
    if stock is None or g2 is None or g2.quantity_kg < Decimal("5.0") or buyer is None:
        return None
    sale = create_sale(
        manager,
        _sale_data(
            farm,
            buyer,
            [
                _line(stock.lot, "g1", "30.0", 18500),
                _line(stock.lot, "g2", "5.0", 15000),
            ],
            notes="Despacho en el camión del comprador.",
        ),
    )
    return attach_invoice(manager, sale.pk, ContentFile(DEMO_INVOICE, name="factura-0001.pdf"))


def _voided_sale(manager, owner, farm):
    stock = _richest(farm, "g1", minimum=Decimal("10.0"))
    buyer = _buyer(owner, "900000003")
    if stock is None or buyer is None:
        return None
    sale = create_sale(manager, _sale_data(farm, buyer, [_line(stock.lot, "g1", "10.0", 18000)]))
    return void_sale(manager, sale.pk, sale.version, "El comprador no recogió el cacao.")


def _richest(farm, grade, *, minimum):
    """La existencia con más kilos del calibre en la finca, si llega a `minimum`."""
    return (
        StockBalance.objects.filter(
            lot__harvest__plot__farm=farm, grade=grade, quantity_kg__gte=minimum
        )
        .select_related("lot")
        .order_by("-quantity_kg", "lot__code")
        .first()
    )


def _buyer(owner, document):
    return Buyer.objects.filter(
        producer=owner.producer, identity_document=document, is_active=True
    ).first()


def _sale_data(farm, buyer, lines, notes=""):
    return {
        "farm_id": farm.pk,
        "buyer_id": buyer.pk,
        "sale_date": timezone.localdate(),
        "notes": notes,
        "lines": lines,
    }


def _line(lot, grade, kilos, price):
    return {"lot_id": lot.pk, "grade": grade, "quantity_kg": Decimal(kilos), "price_per_kg": price}
