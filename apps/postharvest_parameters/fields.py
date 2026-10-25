"""Los parámetros de secado de un productor: cuáles son, de qué tipo y entre qué valores.

Es la única lista: el modelo, sus restricciones, la validación de la API y la lectura de las demás
apps salen de aquí.
"""

from decimal import Decimal

PERCENT = "percent"
DAYS = "days"
HOURS = "hours"

PERCENT_MAX_DIGITS = 4
PERCENT_DECIMAL_PLACES = 1
# Un secado solar dura de 5 a 7 días y, con lluvia, dos o tres semanas. Los topes no los pide
# nadie: atrapan un cero de más (80 días en vez de 8, 480 horas en vez de 48), que no rompe nada
# pero deja las alertas en silencio.
MAX_DAYS = 60
MAX_WINDOW_HOURS = 240

LIMITS = {
    PERCENT: (Decimal("0"), Decimal("100")),
    DAYS: (1, MAX_DAYS),
    HOURS: (1, MAX_WINDOW_HOURS),
}

FIELDS: dict[str, str] = {
    "entry_moisture_min_pct": PERCENT,
    "entry_moisture_max_pct": PERCENT,
    "target_moisture_min_pct": PERCENT,
    "target_moisture_max_pct": PERCENT,
    "estimated_days_min": DAYS,
    "estimated_days_max": DAYS,
    "slow_stall_window_hours": HOURS,
    # Puntos de humedad, no un porcentaje del valor anterior: de 30 % a 26 % son 4 puntos.
    "slow_stall_min_drop_pct": PERCENT,
    "slow_duration_day": DAYS,
    "slow_duration_moisture_pct": PERCENT,
    "accelerated_day": DAYS,
    "accelerated_moisture_pct": PERCENT,
    "near_target_min_pct": PERCENT,
    "near_target_max_pct": PERCENT,
    "overdried_moisture_pct": PERCENT,
}

RANGE_PAIRS = (
    ("entry_moisture_min_pct", "entry_moisture_max_pct"),
    ("target_moisture_min_pct", "target_moisture_max_pct"),
    ("estimated_days_min", "estimated_days_max"),
    ("near_target_min_pct", "near_target_max_pct"),
)

# Una caída de cero haría que todo secado cuente como estancado.
POSITIVE_FIELDS = ("slow_stall_min_drop_pct",)
