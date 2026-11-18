"""El reporte de producción: una fila por cosecha, con su lote y lo que dio su secado."""

from apps.common.contracts.reports import report_source

from ...report import COUNT, DATE, KG, PCT, TEXT, Column, ReportBody, Total
from ...rules import farm_text, kg_sum, place_order, plot_text

COLUMNS = (
    Column("harvest_date", "Fecha", DATE),
    Column("farm", "Finca", TEXT),
    Column("plot", "Parcela", TEXT),
    Column("variety", "Variedad", TEXT),
    Column("collector", "Recolector", TEXT),
    Column("green_kg", "Kg en baba", KG),
    Column("lot_code", "Lote", TEXT),
    Column("lot_status", "Estado del lote", TEXT),
    Column("dry_kg", "Kg seco", KG),
    Column("yield_pct", "Rendimiento %", PCT),
)


def build(scope) -> ReportBody:
    harvests = report_source("harvest_rows")(
        scope.farm_ids, scope.period, plot_id=scope.plot_id, lot_id=scope.lot_id
    )
    lot_ids = [harvest.lot_id for harvest in harvests if harvest.lot_id is not None]
    dried = {result.lot_id: result for result in report_source("drying_results")(lot_ids)}
    harvests.sort(key=lambda harvest: (harvest.harvest_date, *place_order(harvest.place)))
    rows = [_row(harvest, dried.get(harvest.lot_id)) for harvest in harvests]
    green_kg = kg_sum(harvest.green_kg for harvest in harvests)
    dried_green_kg = kg_sum(harvest.green_kg for harvest in harvests if harvest.lot_id in dried)
    return ReportBody(
        columns=COLUMNS,
        rows=rows,
        totals=(
            Total("harvests", "Cosechas", COUNT, len(rows)),
            Total("green_kg", "Kg en baba", KG, green_kg),
            Total("dry_kg", "Kg seco", KG, kg_sum(result.dry_kg for result in dried.values())),
            Total("green_kg_not_dried", "Kg en baba sin secar", KG, green_kg - dried_green_kg),
        ),
    )


def _row(harvest, drying) -> dict:
    return {
        "harvest_date": harvest.harvest_date,
        "farm": farm_text(harvest.place),
        "plot": plot_text(harvest.place),
        "variety": harvest.variety,
        "collector": harvest.collector,
        "green_kg": harvest.green_kg,
        "lot_code": harvest.lot_code,
        "lot_status": harvest.lot_status,
        "dry_kg": drying.dry_kg if drying else None,
        "yield_pct": drying.yield_pct if drying else None,
    }
