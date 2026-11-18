"""El reporte de trazabilidad: un lote por fila, de su cosecha a su venta.

Cada etapa sale de la app que la guarda, pedida solo para los lotes del reporte; una etapa que el
lote todavía no tiene queda vacía, así que un lote en proceso muestra lo que lleva.
"""

from apps.common.contracts.reports import report_source

from ...report import COUNT, DATE, KG, PCT, TEXT, Column, ReportBody, Total
from ...rules import farm_text, kg_sum, place_order, plot_text

COLUMNS = (
    Column("lot_code", "Lote", TEXT),
    Column("farm", "Finca", TEXT),
    Column("plot", "Parcela", TEXT),
    Column("harvest_date", "Fecha de cosecha", DATE),
    Column("green_kg", "Kg en baba", KG),
    Column("status", "Estado actual", TEXT),
    Column("fermentation_started_on", "Inicio de fermentación", DATE),
    Column("fermentation_ended_on", "Fin de fermentación", DATE),
    Column("drying_ended_on", "Fin del secado", DATE),
    Column("dry_kg", "Kg seco", KG),
    Column("yield_pct", "Rendimiento %", PCT),
    Column("quality_result", "Resultado de calidad", TEXT),
    Column("quality_closed_on", "Fecha de calidad", DATE),
    Column("g1_kg", "Kg G1", KG),
    Column("g2_kg", "Kg G2", KG),
    Column("discard_kg", "Kg descarte", KG),
    Column("entry_date", "Ingreso a bodega", DATE),
    Column("available_kg", "Kg disponibles", KG),
    Column("sold_kg", "Kg vendidos", KG),
    Column("buyers", "Compradores", TEXT),
)

STAGE_SOURCES = (
    "fermentation_dates",
    "drying_results",
    "quality_by_lot",
    "stock_by_lot",
    "sales_by_lot",
)


def build(scope) -> ReportBody:
    lots = report_source("lot_rows")(
        scope.farm_ids, scope.period, plot_id=scope.plot_id, lot_id=scope.lot_id
    )
    lot_ids = [lot.lot_id for lot in lots]
    stages = {
        name: {row.lot_id: row for row in report_source(name)(lot_ids)} for name in STAGE_SOURCES
    }
    lots.sort(key=lambda lot: (lot.harvest_date, *place_order(lot.place), lot.code))
    rows = [_row(lot, *(stages[name].get(lot.lot_id) for name in STAGE_SOURCES)) for lot in lots]
    return ReportBody(
        columns=COLUMNS,
        rows=rows,
        totals=(
            Total("lots", "Lotes", COUNT, len(rows)),
            Total("green_kg", "Kg en baba", KG, kg_sum(lot.green_kg for lot in lots)),
            Total(
                "dry_kg",
                "Kg seco",
                KG,
                kg_sum(row.dry_kg for row in stages["drying_results"].values()),
            ),
            Total(
                "sold_kg",
                "Kg vendidos",
                KG,
                kg_sum(row.sold_kg for row in stages["sales_by_lot"].values()),
            ),
        ),
    )


def _row(lot, fermentation, drying, quality, stock, sales) -> dict:
    return {
        "lot_code": lot.code,
        "farm": farm_text(lot.place),
        "plot": plot_text(lot.place),
        "harvest_date": lot.harvest_date,
        "green_kg": lot.green_kg,
        "status": lot.status,
        "fermentation_started_on": fermentation.started_on if fermentation else None,
        "fermentation_ended_on": fermentation.ended_on if fermentation else None,
        "drying_ended_on": drying.ended_on if drying else None,
        "dry_kg": drying.dry_kg if drying else None,
        "yield_pct": drying.yield_pct if drying else None,
        "quality_result": quality.result if quality else None,
        "quality_closed_on": quality.closed_on if quality else None,
        "g1_kg": quality.g1_kg if quality else None,
        "g2_kg": quality.g2_kg if quality else None,
        "discard_kg": quality.discard_kg if quality else None,
        "entry_date": stock.entry_date if stock else None,
        "available_kg": stock.available_kg if stock else None,
        "sold_kg": sales.sold_kg if sales else None,
        "buyers": ", ".join(sales.buyers) if sales else None,
    }
