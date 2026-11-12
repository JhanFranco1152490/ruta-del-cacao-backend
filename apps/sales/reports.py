"""Las ventas en los reportes del productor: las líneas de las registradas, sin las anuladas."""

from collections import defaultdict

from apps.common.codes import format_code
from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import LotSales, SaleRow
from apps.common.figures import ZERO

from .models import SaleLine

REGISTERED = {"sale__voided_at__isnull": True}


def sale_rows(farm_ids, period: IndicatorPeriod, *, plot_id=None, lot_id=None) -> list[SaleRow]:
    lines = SaleLine.objects.filter(
        **REGISTERED,
        sale__farm_id__in=farm_ids,
        sale__sale_date__range=(period.date_from, period.date_to),
    ).select_related("sale__buyer", "sale__farm", "lot")
    if plot_id is not None:
        lines = lines.filter(lot__harvest__plot_id=plot_id)
    if lot_id is not None:
        lines = lines.filter(lot_id=lot_id)
    return [
        SaleRow(
            sale_id=line.sale_id,
            sale_number=line.sale.number,
            sale_date=line.sale.sale_date,
            buyer=line.sale.buyer.name,
            farm_id=line.sale.farm_id,
            farm_code=format_code("F", line.sale.farm.number),
            farm_name=line.sale.farm.name,
            lot_id=line.lot_id,
            lot_code=line.lot.code,
            grade=line.get_grade_display(),
            kg=line.quantity_kg,
            price_per_kg=line.price_per_kg,
            subtotal=line.subtotal,
        )
        for line in lines
    ]


def sales_by_lot(lot_ids) -> list[LotSales]:
    """Lo vendido de cada uno de esos lotes, sin importar cuándo."""
    if not lot_ids:
        return []
    lines = SaleLine.objects.filter(**REGISTERED, lot_id__in=lot_ids).values(
        "lot_id", "quantity_kg", "sale__buyer__name"
    )
    sold = defaultdict(lambda: ZERO)
    buyers = defaultdict(set)
    for line in lines:
        sold[line["lot_id"]] += line["quantity_kg"]
        buyers[line["lot_id"]].add(line["sale__buyer__name"])
    return [
        LotSales(lot_id=lot_id, sold_kg=kg, buyers=tuple(sorted(buyers[lot_id])))
        for lot_id, kg in sold.items()
    ]
