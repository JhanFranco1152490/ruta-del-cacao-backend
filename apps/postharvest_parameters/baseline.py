"""La línea base del secado: lo que usa un productor que nunca cambió sus parámetros o los
restableció. Es la única copia; no se guarda en la base."""

from decimal import Decimal

DRYING_BASELINE = {
    "entry_moisture_min_pct": Decimal("55.0"),
    "entry_moisture_max_pct": Decimal("60.0"),
    "target_moisture_min_pct": Decimal("6.5"),
    "target_moisture_max_pct": Decimal("7.5"),
    "estimated_days_min": 5,
    "estimated_days_max": 7,
    "slow_stall_window_hours": 48,
    "slow_stall_min_drop_pct": Decimal("4.0"),
    "slow_duration_day": 8,
    "slow_duration_moisture_pct": Decimal("10.0"),
    "accelerated_day": 3,
    "accelerated_moisture_pct": Decimal("15.0"),
    "near_target_min_pct": Decimal("7.6"),
    "near_target_max_pct": Decimal("8.5"),
    "overdried_moisture_pct": Decimal("6.0"),
}
