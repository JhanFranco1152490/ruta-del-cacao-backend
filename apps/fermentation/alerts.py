"""Las reglas de los volteos que comparten la pantalla de fermentación y los avisos de volteo
pendiente. Viven en un solo lugar para que lo que la pantalla muestra como pendiente sea lo mismo
que dispara un aviso.

El protocolo de campo voltea la masa a las 48 horas del inicio y después cada 24 horas. No son
parámetros del productor: es la forma de fermentar, igual en cualquier región.
"""

from datetime import datetime, timedelta

FIRST_TURN_AFTER = timedelta(hours=48)
NEXT_TURN_AFTER = timedelta(hours=24)
# Con cuánta anticipación se avisa que se acerca el primer volteo.
FIRST_TURN_WARNING = timedelta(hours=6)


def next_turn_due_at(started_at: datetime, last_turned_at: datetime | None) -> datetime:
    """Cuándo toca el siguiente volteo: 48 horas después del inicio si todavía no hay volteos, o
    24 horas después del último. Es una guía: un volteo se registra a la hora en que se hizo."""
    if last_turned_at is None:
        return started_at + FIRST_TURN_AFTER
    return last_turned_at + NEXT_TURN_AFTER
