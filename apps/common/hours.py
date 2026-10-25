"""Horas entre dos momentos, como las muestran las etapas del lote que se miden en horas (la
fermentación y el secado)."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

ONE_DECIMAL = Decimal("0.1")


def hours_between(start: datetime, end: datetime) -> Decimal:
    """Las horas entre dos momentos, con un decimal (mitad hacia arriba), como las muestra la
    pantalla: 2 h 3 min son 2,1 h."""
    seconds = Decimal(int((end - start).total_seconds()))
    return (seconds / 3600).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)
