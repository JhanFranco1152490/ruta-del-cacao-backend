"""Lo que cada variedad de cacao produjo y dejó de calidad en el periodo, para los dos paneles."""

from apps.common.contracts.indicators import IndicatorPeriod, indicator_source

from ..rules import ZERO, one_decimal, quality_split
from .totals import sum_by


def variety_rows(farm_ids, period: IndicatorPeriod) -> list[dict]:
    """Una fila por variedad con alguna cifra en el periodo, de la que más kg en baba tiene a la
    que menos. La calidad y el seco no dependen de que la variedad también haya cosechado en el
    periodo: una clasificación puede cerrar en un mes distinto al de su cosecha."""
    green = indicator_source("harvest_varieties")(farm_ids, period)
    dry = indicator_source("drying_varieties")(farm_ids, period)
    quality = indicator_source("quality_varieties")(farm_ids, period)
    names = {row.variety_id: row.name for row in [*green, *dry, *quality]}
    green_by = sum_by(green, "variety_id", "kg")
    dry_by = sum_by(dry, "variety_id", "kg")
    quality_by = {row.variety_id: row for row in quality}
    rows = [
        _variety_row(variety_id, name, green_by, dry_by, quality_by.get(variety_id))
        for variety_id, name in names.items()
    ]
    rows.sort(key=lambda row: (-row["green_kg"], row["variety_name"]))
    return rows


def _variety_row(variety_id, name: str, green_by: dict, dry_by: dict, quality) -> dict:
    return {
        "variety_id": variety_id,
        "variety_name": name,
        "green_kg": one_decimal(green_by.get(variety_id, ZERO)),
        "dry_kg": one_decimal(dry_by.get(variety_id, ZERO)),
        **quality_split(
            quality.g1_kg if quality else ZERO,
            quality.g2_kg if quality else ZERO,
            quality.discard_kg if quality else ZERO,
        ),
    }
