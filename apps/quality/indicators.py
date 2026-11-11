"""La calidad de los paneles de indicadores: lo clasificado y lo descartado por finca, con la fecha
de cierre en el periodo, como la pestaña de lotes cerrados."""

from apps.common.contracts.indicators import FarmQuality, IndicatorPeriod

from .services.queries import Lot, closed_in_period, closed_kg, closed_totals

FARM = "harvest__plot__farm_id"


def quality_by_farm(farm_ids, period: IndicatorPeriod) -> list[FarmQuality]:
    lots = closed_in_period(
        Lot.objects.filter(**{f"{FARM}__in": farm_ids}),
        {"closed_from": period.date_from, "closed_to": period.date_to},
    )
    rows = lots.values(FARM).annotate(**closed_totals()).order_by()
    return [_row(row) for row in rows]


def _row(row: dict) -> FarmQuality:
    kg = closed_kg(row)
    return FarmQuality(
        farm_id=row[FARM],
        g1_kg=kg["g1_kg"],
        g2_kg=kg["g2_kg"],
        discard_kg=kg["discarded_kg"],
        lots_classified=row["classified"],
        lots_discarded=row["discarded"],
    )
