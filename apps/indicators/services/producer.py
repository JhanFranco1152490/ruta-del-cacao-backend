"""El panel del productor: su unidad productiva por parcela, con calidad, existencias y ventas.

Todo sale de las fuentes que registran las demás apps; aquí solo se combinan y se calculan los kg
por hectárea, los porcentajes y los meses.
"""

from collections import defaultdict

from apps.common.contracts.indicators import IndicatorPeriod, indicator_source
from apps.common.figures import ZERO, code_order, one_decimal, sum_by

from ..exceptions import IndicatorFarmNotFound
from ..rules import month_series, per_hectare
from .totals import production_by_month, sales_totals, sold_by_month, total_quality


def producer_indicators(actor, period: IndicatorPeriod, *, farm_id=None, producer_id=None):
    farm_ids = indicator_source("farm_scope")(actor, farm_id=farm_id, producer_id=producer_id)
    if farm_id is not None and not farm_ids.exists():
        raise IndicatorFarmNotFound()
    farms = {farm.farm_id: farm for farm in indicator_source("farms")(farm_ids)}
    sales = indicator_source("sales")(farm_ids, period)
    return {
        "period": {"from": period.date_from, "to": period.date_to},
        "production": _production(farm_ids, period, farms),
        "quality": total_quality(indicator_source("quality")(farm_ids, period)),
        "inventory": _inventory(indicator_source("warehouse")(farm_ids), farms),
        "sales": {
            **sales_totals(sales),
            "months": month_series(period.months(), sold_by_month(sales), ("sold_kg",)),
        },
    }


def _production(farm_ids, period: IndicatorPeriod, farms: dict) -> dict:
    harvested = indicator_source("harvests")(farm_ids, period)
    dried = indicator_source("drying")(farm_ids, period)
    green_by_plot = sum_by(harvested, "plot_id", "kg")
    dry_by_plot = sum_by(dried, "plot_id", "dry_kg")
    # Una parcela inactiva solo cuenta si cosechó en el periodo: lo que produjo no desaparece al
    # desactivarla, pero su área ya no es área que produce.
    plots = sorted(
        (
            plot
            for plot in indicator_source("plots")(farm_ids)
            if plot.is_active or plot.plot_id in green_by_plot
        ),
        key=lambda plot: (code_order(farms[plot.farm_id].code), code_order(plot.code)),
    )
    green_kg = sum(green_by_plot.values(), ZERO)
    dry_kg = sum(dry_by_plot.values(), ZERO)
    area = sum((plot.area_hectares for plot in plots), ZERO)
    months = production_by_month(harvested, dried)
    return {
        "green_kg": one_decimal(green_kg),
        "dry_kg": one_decimal(dry_kg),
        "green_kg_not_dried": one_decimal(green_kg - sum((row.green_kg for row in dried), ZERO)),
        "area_hectares": area,
        "green_kg_per_hectare": per_hectare(green_kg, area),
        "dry_kg_per_hectare": per_hectare(dry_kg, area),
        "plots": [
            _plot_row(plot, farms[plot.farm_id], green_by_plot, dry_by_plot) for plot in plots
        ],
        "months": month_series(period.months(), months, ("green_kg", "dry_kg")),
    }


def _plot_row(plot, farm, green_by_plot: dict, dry_by_plot: dict) -> dict:
    green = green_by_plot.get(plot.plot_id, ZERO)
    dry = dry_by_plot.get(plot.plot_id, ZERO)
    return {
        "plot_id": plot.plot_id,
        "plot_code": plot.code,
        "plot_name": plot.name,
        "farm_id": plot.farm_id,
        "farm_code": farm.code,
        "farm_name": farm.name,
        "is_active": plot.is_active,
        "area_hectares": plot.area_hectares,
        "green_kg": one_decimal(green),
        "dry_kg": one_decimal(dry),
        "green_kg_per_hectare": per_hectare(green, plot.area_hectares),
        "dry_kg_per_hectare": per_hectare(dry, plot.area_hectares),
    }


def _inventory(rows, farms: dict) -> dict:
    by_farm = defaultdict(lambda: {"g1": ZERO, "g2": ZERO})
    for row in rows:
        by_farm[row.farm_id][row.grade] += row.kg
    g1 = sum((kg["g1"] for kg in by_farm.values()), ZERO)
    g2 = sum((kg["g2"] for kg in by_farm.values()), ZERO)
    return {
        "g1_kg": one_decimal(g1),
        "g2_kg": one_decimal(g2),
        "total_kg": one_decimal(g1 + g2),
        "farms": [
            {
                "farm_id": farm_id,
                "farm_code": farms[farm_id].code,
                "farm_name": farms[farm_id].name,
                "g1_kg": one_decimal(kg["g1"]),
                "g2_kg": one_decimal(kg["g2"]),
            }
            for farm_id, kg in sorted(
                by_farm.items(), key=lambda item: code_order(farms[item[0]].code)
            )
        ],
    }
