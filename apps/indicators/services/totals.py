"""Lo que los dos paneles suman igual: la calidad y las ventas de un conjunto de fincas."""

from collections import defaultdict

from ..rules import ZERO, one_decimal, quality_split


def total_quality(rows) -> dict:
    return {
        **quality_split(
            sum((row.g1_kg for row in rows), ZERO),
            sum((row.g2_kg for row in rows), ZERO),
            sum((row.discard_kg for row in rows), ZERO),
        ),
        "lots_classified": sum(row.lots_classified for row in rows),
        "lots_discarded": sum(row.lots_discarded for row in rows),
    }


def sales_totals(rows) -> dict:
    g1 = sum((row.g1_kg for row in rows), ZERO)
    g2 = sum((row.g2_kg for row in rows), ZERO)
    return {
        "sold_kg": one_decimal(g1 + g2),
        "g1_kg": one_decimal(g1),
        "g2_kg": one_decimal(g2),
        "sales": sum(row.sales for row in rows),
    }


def production_by_month(harvested, dried) -> dict[str, dict]:
    """Los kg en baba y secos de cada mes con datos; `month_series` completa los demás."""
    months = defaultdict(dict)
    for month, kg in sum_by(harvested, "month", "kg").items():
        months[month]["green_kg"] = kg
    for month, kg in sum_by(dried, "month", "dry_kg").items():
        months[month]["dry_kg"] = kg
    return dict(months)


def sold_by_month(rows) -> dict[str, dict]:
    months = defaultdict(lambda: {"sold_kg": ZERO})
    for row in rows:
        months[row.month]["sold_kg"] += row.g1_kg + row.g2_kg
    return dict(months)


def sum_by(rows, key: str, value: str) -> dict:
    """La suma de `value` de las filas agrupadas por `key`, sin las claves que no aparecen."""
    totals = defaultdict(lambda: ZERO)
    for row in rows:
        totals[getattr(row, key)] += getattr(row, value)
    return dict(totals)
