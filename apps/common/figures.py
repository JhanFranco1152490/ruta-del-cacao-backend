"""Las cuentas de las cifras que se muestran sumadas (paneles y reportes): funciones puras sobre
`Decimal`, sin consultas."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
ONE_DECIMAL = Decimal("0.1")


def one_decimal(value: Decimal) -> Decimal:
    return value.quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def code_order(code: str) -> tuple[int, str]:
    """El orden de un código de finca o parcela: `F99` antes que `F100`. Comparados como texto
    quedarían al revés, porque el código tiene al menos dos cifras pero puede tener más."""
    return len(code), code


def percentage(part: Decimal, total: Decimal) -> Decimal | None:
    """Sin total no hay porcentaje: «sin datos» no es «0 %». Cada porcentaje se redondea por su
    lado, así que los de un reparto pueden sumar 99,9 o 100,1."""
    if not total:
        return None
    return one_decimal(part * 100 / total)


def quality_split(g1_kg: Decimal, g2_kg: Decimal, discard_kg: Decimal) -> dict:
    classified_kg = g1_kg + g2_kg + discard_kg
    return {
        "classified_kg": one_decimal(classified_kg),
        "g1_kg": one_decimal(g1_kg),
        "g2_kg": one_decimal(g2_kg),
        "discard_kg": one_decimal(discard_kg),
        "g1_pct": percentage(g1_kg, classified_kg),
        "g2_pct": percentage(g2_kg, classified_kg),
        "discard_pct": percentage(discard_kg, classified_kg),
    }


def sum_by(rows, key: str, value: str) -> dict:
    """La suma de `value` de las filas agrupadas por `key`, sin las claves que no aparecen."""
    totals = defaultdict(lambda: ZERO)
    for row in rows:
        totals[getattr(row, key)] += getattr(row, value)
    return dict(totals)
