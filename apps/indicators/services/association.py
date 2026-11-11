"""El panel de la asociación: la producción, la calidad y los kg vendidos de cada finca de los
productores, sin parcelas, lotes ni existencias.

Esas tres cosas no se calculan, no solo no se muestran: el panel no pide las fuentes de parcelas
ni de bodega, y lo que pide ya viene agregado por finca.
"""

from collections import defaultdict

from apps.common.contracts.indicators import IndicatorPeriod, indicator_source

from ..rules import ZERO, month_series, one_decimal, quality_split
from .totals import production_by_month, sales_totals, sold_by_month, sum_by, total_quality


def association_indicators(actor, period: IndicatorPeriod) -> dict:
    farm_ids = indicator_source("farm_scope")(actor, everyone=True)
    harvested = indicator_source("harvests")(farm_ids, period)
    dried = indicator_source("drying")(farm_ids, period)
    quality = indicator_source("quality")(farm_ids, period)
    sales = indicator_source("sales")(farm_ids, period)
    green = sum_by(harvested, "farm_id", "kg")
    dry = sum_by(dried, "farm_id", "dry_kg")
    quality_by_farm = {row.farm_id: row for row in quality}
    sold = defaultdict(lambda: ZERO)
    for row in sales:
        sold[row.farm_id] += row.g1_kg + row.g2_kg
    # Solo las fincas con alguna cifra: una fila en cero por cada finca taparía las que produjeron.
    with_figures = set(green) | set(dry) | set(quality_by_farm) | set(sold)
    farms = indicator_source("farms")(list(with_figures)) if with_figures else []
    rows = [_farm_row(farm, green, dry, quality_by_farm.get(farm.farm_id), sold) for farm in farms]
    rows.sort(key=lambda row: (-row["green_kg"], row["farm_name"]))
    return {
        "period": {"from": period.date_from, "to": period.date_to},
        "totals": {
            "producers": len({farm.producer_id for farm in farms}),
            "farms": len(farms),
            "green_kg": one_decimal(sum(green.values(), ZERO)),
            "dry_kg": one_decimal(sum(dry.values(), ZERO)),
            **_without_lots(total_quality(quality)),
            "sold_kg": sales_totals(sales)["sold_kg"],
        },
        "months": month_series(
            period.months(),
            _by_month(harvested, dried, sales),
            ("green_kg", "dry_kg", "sold_kg"),
        ),
        "farms": rows,
    }


def _farm_row(farm, green: dict, dry: dict, quality, sold: dict) -> dict:
    split = quality_split(
        quality.g1_kg if quality else ZERO,
        quality.g2_kg if quality else ZERO,
        quality.discard_kg if quality else ZERO,
    )
    return {
        "farm_id": farm.farm_id,
        "farm_code": farm.code,
        "farm_name": farm.name,
        "municipality_code": farm.municipality_code,
        "producer": {
            "id": farm.producer_id,
            "member_code": farm.producer_member_code,
            "first_name": farm.producer_first_name,
            "last_name": farm.producer_last_name,
        },
        "green_kg": one_decimal(green.get(farm.farm_id, ZERO)),
        "dry_kg": one_decimal(dry.get(farm.farm_id, ZERO)),
        **split,
        "sold_kg": one_decimal(sold.get(farm.farm_id, ZERO)),
    }


def _without_lots(quality: dict) -> dict:
    """La calidad sin cuántos lotes: la asociación no ve nada por lote."""
    return {key: value for key, value in quality.items() if not key.startswith("lots_")}


def _by_month(harvested, dried, sales) -> dict[str, dict]:
    months = defaultdict(dict, production_by_month(harvested, dried))
    for month, sold in sold_by_month(sales).items():
        months[month].update(sold)
    return months
