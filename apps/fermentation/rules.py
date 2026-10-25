"""Las cuentas de una fermentación que no dependen de la base: el número de cada volteo. Las
horas entre dos momentos son comunes con el secado (`apps/common/hours.py`)."""


def numbered(turns) -> list[tuple[int, object]]:
    """Cada volteo con su número, que es su posición por hora: el primero es el 1. No depende del
    orden en que llegaron, para que uno registrado sin conexión que llega tarde quede en su
    lugar."""
    ordered = sorted(turns, key=lambda turn: turn.turned_at)
    return list(enumerate(ordered, start=1))
