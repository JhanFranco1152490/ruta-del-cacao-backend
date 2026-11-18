"""El reporte de comercialización: una fila por línea de las ventas registradas, con su precio."""

from apps.common.contracts.reports import report_source
from apps.common.figures import code_order

from ...report import COUNT, DATE, KG, MONEY, TEXT, Column, ReportBody, Total
from ...rules import kg_sum, labeled

COLUMNS = (
    Column("sale_date", "Fecha", DATE),
    Column("sale_number", "Venta", TEXT),
    Column("buyer", "Comprador", TEXT),
    Column("farm", "Finca", TEXT),
    Column("lot_code", "Lote", TEXT),
    Column("grade", "Calibre", TEXT),
    Column("kg", "Kg", KG),
    Column("price_per_kg", "Precio por kg", MONEY),
    Column("subtotal", "Subtotal", MONEY),
)


def build(scope) -> ReportBody:
    lines = report_source("sale_rows")(
        scope.farm_ids, scope.period, plot_id=scope.plot_id, lot_id=scope.lot_id
    )
    lines.sort(
        key=lambda line: (line.sale_date, code_order(line.sale_number), line.lot_code, line.grade)
    )
    g1_kg = kg_sum(line.kg for line in lines if line.grade == "G1")
    g2_kg = kg_sum(line.kg for line in lines if line.grade == "G2")
    return ReportBody(
        columns=COLUMNS,
        rows=[_row(line) for line in lines],
        totals=(
            # Una venta con dos calibres son dos líneas: se cuenta una vez.
            Total("sales", "Ventas", COUNT, len({line.sale_id for line in lines})),
            Total("g1_kg", "Kg G1", KG, g1_kg),
            Total("g2_kg", "Kg G2", KG, g2_kg),
            Total("sold_kg", "Kg vendidos", KG, g1_kg + g2_kg),
            Total("total_value", "Valor total", MONEY, sum(line.subtotal for line in lines)),
        ),
    )


def _row(line) -> dict:
    return {
        "sale_date": line.sale_date,
        "sale_number": line.sale_number,
        "buyer": line.buyer,
        "farm": labeled(line.farm_code, line.farm_name),
        "lot_code": line.lot_code,
        "grade": line.grade,
        "kg": line.kg,
        "price_per_kg": line.price_per_kg,
        "subtotal": line.subtotal,
    }
