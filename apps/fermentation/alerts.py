"""Las reglas de los volteos que comparten la pantalla de fermentación y los avisos de volteo
pendiente. Viven en un solo lugar para que lo que la pantalla muestra como pendiente sea lo mismo
que dispara un aviso.

El protocolo de campo voltea la masa a las 48 horas del inicio y después cada 24 horas; son los
valores de la línea base de los parámetros de poscosecha, que cada productor puede ajustar a su
región.
"""

from datetime import datetime, timedelta

from apps.common.contracts.postharvest_parameters import FermentationParameters

# Con cuánta anticipación se avisa que se acerca el primer volteo.
FIRST_TURN_WARNING = timedelta(hours=6)


def next_turn_due_at(
    started_at: datetime, last_turned_at: datetime | None, parameters: FermentationParameters
) -> datetime:
    """Cuándo toca el siguiente volteo: las horas del primer volteo después del inicio si todavía
    no hay volteos, o las de los siguientes después del último (48 y 24 en la línea base). Es una
    guía: un volteo se registra a la hora en que se hizo."""
    if last_turned_at is None:
        return started_at + timedelta(hours=parameters.first_turn_hours)
    return last_turned_at + timedelta(hours=parameters.next_turn_hours)
