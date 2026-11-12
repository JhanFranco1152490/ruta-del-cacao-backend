"""El reporte de inventario: lo que hay hoy en bodega, una fila por lote, calibre y lugar."""

from apps.common.contracts.reports import report_source
from apps.common.figures import code_order

from ...report import DATE, KG, TEXT, Column, ReportBody, Total
from ...rules import farm_text, kg_sum

COLUMNS = (
    Column("lot_code", "Lote", TEXT),
    Column("farm", "Finca", TEXT),
    Column("warehouse", "Bodega", TEXT),
    Column("location", "Ubicación", TEXT),
    Column("grade", "Calibre", TEXT),
    Column("kg", "Kg disponibles", KG),
    Column("entry_date", "Fecha de ingreso", DATE),
)


def build(scope) -> ReportBody:
    stock = report_source("stock_rows")(scope.farm_ids, plot_id=scope.plot_id, lot_id=scope.lot_id)
    stock.sort(
        key=lambda item: (
            code_order(item.place.farm_code),
            item.lot_code,
            item.grade,
            item.warehouse,
            item.location,
        )
    )
    g1_kg = kg_sum(item.kg for item in stock if item.grade == "G1")
    g2_kg = kg_sum(item.kg for item in stock if item.grade == "G2")
    return ReportBody(
        columns=COLUMNS,
        rows=[_row(item) for item in stock],
        totals=(
            Total("g1_kg", "Kg G1", KG, g1_kg),
            Total("g2_kg", "Kg G2", KG, g2_kg),
            Total("total_kg", "Kg totales", KG, g1_kg + g2_kg),
        ),
    )


def _row(item) -> dict:
    return {
        "lot_code": item.lot_code,
        "farm": farm_text(item.place),
        "warehouse": item.warehouse,
        "location": item.location,
        "grade": item.grade,
        "kg": item.kg,
        "entry_date": item.entry_date,
    }
