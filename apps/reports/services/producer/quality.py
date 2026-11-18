"""El reporte de calidad: una fila por lote cerrado en el periodo, clasificado o descartado."""

from apps.common.contracts.reports import report_source
from apps.common.figures import percentage, quality_split

from ...report import COUNT, DATE, KG, PCT, TEXT, Column, ReportBody, Total
from ...rules import farm_text, kg_sum, place_order, plot_text, reason_text

COLUMNS = (
    Column("lot_code", "Lote", TEXT),
    Column("farm", "Finca", TEXT),
    Column("plot", "Parcela", TEXT),
    Column("closed_on", "Fecha de cierre", DATE),
    Column("result", "Resultado", TEXT),
    Column("dry_kg", "Kg seco", KG),
    Column("g1_kg", "Kg G1", KG),
    Column("g2_kg", "Kg G2", KG),
    Column("discard_kg", "Kg descarte", KG),
    Column("g1_pct", "% G1", PCT),
    Column("g2_pct", "% G2", PCT),
    Column("discard_pct", "% descarte", PCT),
    Column("discard_reason", "Motivo del descarte", TEXT),
)

SPLIT_TOTALS = (
    ("classified_kg", "Kg clasificados", KG),
    ("g1_kg", "Kg G1", KG),
    ("g2_kg", "Kg G2", KG),
    ("discard_kg", "Kg descarte", KG),
    ("g1_pct", "% G1", PCT),
    ("g2_pct", "% G2", PCT),
    ("discard_pct", "% descarte", PCT),
)


def build(scope) -> ReportBody:
    lots = report_source("quality_rows")(
        scope.farm_ids, scope.period, plot_id=scope.plot_id, lot_id=scope.lot_id
    )
    lots.sort(key=lambda lot: (lot.closed_on, *place_order(lot.place), lot.lot_code))
    discarded = sum(1 for lot in lots if lot.whole_discard)
    split = quality_split(
        kg_sum(lot.g1_kg for lot in lots),
        kg_sum(lot.g2_kg for lot in lots),
        kg_sum(lot.discard_kg for lot in lots),
    )
    return ReportBody(
        columns=COLUMNS,
        rows=[_row(lot) for lot in lots],
        totals=(
            Total("lots_classified", "Lotes clasificados", COUNT, len(lots) - discarded),
            Total("lots_discarded", "Lotes descartados", COUNT, discarded),
            *(Total(key, label, kind, split[key]) for key, label, kind in SPLIT_TOTALS),
        ),
    )


def _row(lot) -> dict:
    total = lot.g1_kg + lot.g2_kg + lot.discard_kg
    return {
        "lot_code": lot.lot_code,
        "farm": farm_text(lot.place),
        "plot": plot_text(lot.place),
        "closed_on": lot.closed_on,
        "result": lot.result,
        "dry_kg": lot.dry_kg,
        "g1_kg": lot.g1_kg,
        "g2_kg": lot.g2_kg,
        "discard_kg": lot.discard_kg,
        "g1_pct": percentage(lot.g1_kg, total),
        "g2_pct": percentage(lot.g2_kg, total),
        "discard_pct": percentage(lot.discard_kg, total),
        "discard_reason": reason_text(lot.discard_reason, lot.discard_detail),
    }
