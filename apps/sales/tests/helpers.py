from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.buyers.tests.factories import BuyerFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory
from apps.warehouse.tests.factories import StockExitFactory, WarehouseFactory
from apps.warehouse.tests.helpers import classified_lot, stored_lot

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


class Market:
    """Un productor con dos fincas. En A: una bodega con dos lotes En bodega (250,0 kg de G1 y 55,2
    de G2 cada uno) y un lote Clasificado. En B: un lote En bodega. Dos compradores, uno inactivo.
    """

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm = FarmFactory(producer=self.producer, number=1)
        self.other_farm = FarmFactory(producer=self.producer, number=2)
        plot = characterized_plot(farm=self.farm)
        other_plot = characterized_plot(farm=self.other_farm)
        warehouse = WarehouseFactory(farm=self.farm)
        self.lot, _ = stored_lot(plot, warehouse)
        self.second_lot, _ = stored_lot(plot, warehouse)
        self.classified = classified_lot(plot)
        self.other_farm_lot, _ = stored_lot(other_plot, WarehouseFactory(farm=self.other_farm))
        self.buyer = BuyerFactory(producer=self.producer)
        self.inactive_buyer = BuyerFactory(producer=self.producer, is_active=False)
        self.owner = make_producer_owner(self.producer)

    def body(self, *lines, **overrides) -> dict:
        lines = lines or (self.line(self.lot, "g1", "150.0", 18500),)
        data = {
            "farm_id": str(self.farm.pk),
            "buyer_id": str(self.buyer.pk),
            "sale_date": timezone.localdate().isoformat(),
            "notes": "",
            "lines": list(lines),
        }
        data.update(overrides)
        return data

    @staticmethod
    def line(lot, grade, kilos, price) -> dict:
        return {"lot_id": str(lot.pk), "grade": grade, "quantity_kg": kilos, "price_per_kg": price}
