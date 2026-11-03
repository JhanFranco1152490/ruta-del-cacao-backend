"""Las reglas de calidad que no dependen de la base: se prueban solas."""

from decimal import Decimal

from .exceptions import QualitySumExceeds100
from .models import MAX_PERCENT


def percentages_total(well_fermented: Decimal, moldy: Decimal, other_defects: Decimal) -> Decimal:
    return well_fermented + moldy + other_defects


def check_percentages_total(well_fermented: Decimal, moldy: Decimal, other_defects: Decimal):
    """Los tres porcentajes son partes de la misma muestra: juntos no pasan de 100. El resto son
    granos que no caen en ninguna de las tres (violetas, pizarrosos)."""
    total = percentages_total(well_fermented, moldy, other_defects)
    if total > MAX_PERCENT:
        raise QualitySumExceeds100(total)
