"""Las cuentas del secado que no dependen de la base: el día de secado de una fecha, las horas que
tuvo un día dentro del secado y el rendimiento."""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.common.hours import ONE_DECIMAL, hours_between

NO_HOURS = Decimal("0.0")


def day_number(log_date: date, started_at: datetime) -> int:
    """El día de secado de una fecha: el día 1 es la fecha local del inicio, aunque haya empezado
    a media tarde. Se cuenta por fecha, así que un día sin bitácora sigue contando."""
    return (log_date - timezone.localdate(started_at)).days + 1


def available_hours(log_date: date, started_at: datetime, now: datetime) -> Decimal:
    """Las horas de esa fecha que caen dentro del secado: el día del inicio desde la hora de
    inicio, hoy hasta ahora y los demás días completos. Las horas al sol y a la sombra de ese día
    no pueden pasar de ahí."""
    day_start = datetime.combine(log_date, time.min, tzinfo=timezone.get_current_timezone())
    start = max(day_start, started_at)
    end = min(day_start + timedelta(days=1), now)
    if end <= start:
        return NO_HOURS
    return hours_between(start, end)


def compute_yield(dry_weight_kg: Decimal, green_weight_kg: Decimal) -> Decimal:
    """El rendimiento: peso seco ÷ peso en verde × 100, con un decimal (mitad hacia arriba)."""
    return (dry_weight_kg / green_weight_kg * 100).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)
