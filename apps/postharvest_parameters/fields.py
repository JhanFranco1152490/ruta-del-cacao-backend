"""Los parámetros de poscosecha de un productor (secado y fermentación): cuáles son, de qué tipo y
entre qué valores.

Es la única lista: el modelo, sus restricciones, la validación de la API y la lectura de las demás
apps salen de aquí.
"""

from decimal import Decimal

PERCENT = "percent"
DAYS = "days"
HOURS = "hours"
# Las horas que esperan los volteos de la fermentación; el mismo tope que una ventana de secado.
TURN_HOURS = "turn_hours"
TEMPERATURE = "temperature"
PH = "ph"

PERCENT_MAX_DIGITS = 4
PERCENT_DECIMAL_PLACES = 1
TEMPERATURE_MAX_DIGITS = 4
TEMPERATURE_DECIMAL_PLACES = 1
PH_MAX_DIGITS = 4
PH_DECIMAL_PLACES = 2
# Un secado solar dura de 5 a 7 días y, con lluvia, dos o tres semanas. Los topes no los pide
# nadie: atrapan un cero de más (80 días en vez de 8, 480 horas en vez de 48), que no rompe nada
# pero deja las alertas en silencio.
MAX_DAYS = 60
MAX_WINDOW_HOURS = 240

LIMITS = {
    PERCENT: (Decimal("0"), Decimal("100")),
    DAYS: (1, MAX_DAYS),
    HOURS: (1, MAX_WINDOW_HOURS),
    TURN_HOURS: (1, MAX_WINDOW_HOURS),
    # Los mismos rangos que acepta un volteo: de 0 a 80 °C y de 0 a 14 de pH.
    TEMPERATURE: (Decimal("0"), Decimal("80")),
    PH: (Decimal("0"), Decimal("14")),
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
    # El protocolo de campo voltea a las 48 horas del inicio y después cada 24; la temperatura y el
    # pH son de referencia al registrar un volteo, no los bloquean.
    "first_turn_hours": TURN_HOURS,
    "next_turn_hours": TURN_HOURS,
    "temperature_min_c": TEMPERATURE,
    "temperature_max_c": TEMPERATURE,
    "ph_min": PH,
    "ph_max": PH,
}

# Los quince de secado y los seis de fermentación, cada grupo en lo que lee su app.
FERMENTATION_FIELDS = (
    "first_turn_hours",
    "next_turn_hours",
    "temperature_min_c",
    "temperature_max_c",
    "ph_min",
    "ph_max",
)
DRYING_FIELDS = tuple(name for name in FIELDS if name not in FERMENTATION_FIELDS)

RANGE_PAIRS = (
    ("entry_moisture_min_pct", "entry_moisture_max_pct"),
    ("target_moisture_min_pct", "target_moisture_max_pct"),
    ("estimated_days_min", "estimated_days_max"),
    ("near_target_min_pct", "near_target_max_pct"),
    ("temperature_min_c", "temperature_max_c"),
    ("ph_min", "ph_max"),
)

# Una caída de cero haría que todo secado cuente como estancado.
POSITIVE_FIELDS = ("slow_stall_min_drop_pct",)

# Cuántos decimales lleva cada tipo de valor decimal, para escribirlos como los entrega la API.
DECIMAL_PLACES = {
    PERCENT: PERCENT_DECIMAL_PLACES,
    TEMPERATURE: TEMPERATURE_DECIMAL_PLACES,
    PH: PH_DECIMAL_PLACES,
}
