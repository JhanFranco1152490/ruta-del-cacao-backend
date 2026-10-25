"""Las cuentas de una fermentación que no dependen de la base: horas, duración y número de cada
volteo."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

ONE_DECIMAL = Decimal("0.1")


def hours_between(start: datetime, end: datetime) -> Decimal:
    """Las horas entre dos momentos, con un decimal (mitad hacia arriba), como las muestra la
    pantalla: 2 h 3 min son 2,1 h."""
    seconds = Decimal(int((end - start).total_seconds()))
    return (seconds / 3600).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def numbered(turns) -> list[tuple[int, object]]:
    """Cada volteo con su número, que es su posición por hora: el primero es el 1. No depende del
    orden en que llegaron, para que uno registrado sin conexión que llega tarde quede en su
    lugar."""
    ordered = sorted(turns, key=lambda turn: turn.turned_at)
    return list(enumerate(ordered, start=1))
