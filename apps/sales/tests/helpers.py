from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.warehouse.tests.factories import StockExitFactory

from .factories import SaleFactory, SaleLineFactory


def sale_with_lines(
    farm, *, lines=(("g1", "150.0", 18500),), voided=False, plot=None, lot=None, **fields
):
    """Una venta de `farm` con una línea por cada `(calibre, kilos, precio)`, sin los servicios: no
    descuenta existencias. Cada línea lleva su salida por venta y, si no se da `lot`, su propio
    lote de esa finca."""
    plot = plot or (None if lot else characterized_plot(farm=farm))
    sale = SaleFactory(farm=farm, **fields)
    for grade, kilos, price in lines:
        line_lot = lot or LotFactory(harvest__plot=plot, status=LotStatus.IN_WAREHOUSE)
        stock_exit = StockExitFactory(
            lot=line_lot, grade=grade, quantity_kg=Decimal(kilos), reason="sale"
        )
        SaleLineFactory(sale=sale, stock_exit=stock_exit, price_per_kg=price)
    if voided:
        sale.voided_by = sale.created_by
        sale.voided_at = timezone.now()
        sale.void_reason = "Error de digitación"
        sale.save(update_fields=["voided_by", "voided_at", "void_reason"])
    return sale


def month_of(day: date) -> dict:
    """El mes de `day`, como lo pide la lista."""
    start = day.replace(day=1)
    following = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {"from": start.isoformat(), "to": (following - timedelta(days=1)).isoformat()}
