"""La línea base de la poscosecha: lo que usa un productor que nunca cambió sus parámetros o los
restableció. Es la única copia; no se guarda en la base."""

from dataclasses import asdict
from decimal import Decimal

from apps.common.contracts.postharvest_parameters import DryingParameters, FermentationParameters

DRYING_BASELINE = DryingParameters(
    entry_moisture_min_pct=Decimal("55.0"),
    entry_moisture_max_pct=Decimal("60.0"),
    target_moisture_min_pct=Decimal("6.5"),
    target_moisture_max_pct=Decimal("7.5"),
    estimated_days_min=5,
    estimated_days_max=7,
    slow_stall_window_hours=48,
    slow_stall_min_drop_pct=Decimal("4.0"),
    slow_duration_day=8,
    slow_duration_moisture_pct=Decimal("10.0"),
    accelerated_day=3,
    accelerated_moisture_pct=Decimal("15.0"),
    near_target_min_pct=Decimal("7.6"),
    near_target_max_pct=Decimal("8.5"),
    overdried_moisture_pct=Decimal("6.0"),
)

# La historia no trae valores de fermentación: el primer volteo a las 48 horas y los siguientes
# cada 24 son el protocolo de campo, y la temperatura y el pH son rangos de referencia habituales.
FERMENTATION_BASELINE = FermentationParameters(
    first_turn_hours=48,
    next_turn_hours=24,
    temperature_min_c=Decimal("40.0"),
    temperature_max_c=Decimal("50.0"),
    ph_min=Decimal("4.00"),
    ph_max=Decimal("5.50"),
)

# Los veintiún valores juntos, como los guarda y los entrega la API.
BASELINE_VALUES = {**asdict(DRYING_BASELINE), **asdict(FERMENTATION_BASELINE)}
