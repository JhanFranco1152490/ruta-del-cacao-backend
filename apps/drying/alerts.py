"""Los avisos de desvío del secado: secado lento, acelerado, próximo a la meta y sobresecado.

El servicio de la bitácora llama a `drying_log_alerts` al registrar y al corregir, con la bitácora
ya guardada, y manda lo que devuelve a notificar. Los umbrales son los del productor
(`drying_parameters`), o la línea base si no guardó los suyos. La humedad se compara en puntos: de
30 % a 26 % bajó 4 puntos.
"""

from datetime import timedelta
from decimal import Decimal

from apps.common.contracts.alerts import Deviation, NotificationDraft
from apps.common.contracts.postharvest_parameters import DryingParameters, drying_parameters
from apps.common.contracts.schedulers import FarmAccounts
from apps.common.exceptions import log_unhandled_error

from .models import DryingLogEntry

LOG_PERMISSION = "drying.log_drying"

SLOW_STALLED = "drying_slow_stalled"
SLOW_DURATION = "drying_slow_duration"
ACCELERATED = "drying_accelerated"
NEAR_TARGET = "drying_near_target"
OVERDRIED = "drying_overdried"
DEVIATION_KINDS = (SLOW_STALLED, SLOW_DURATION, ACCELERATED, NEAR_TARGET, OVERDRIED)

NORMAL = "normal"
# El sobresecado va primero y destacado: el grano pierde peso y se quiebra, y lo único que lo
# detiene es sacarlo del sol de inmediato.
CRITICAL = "critical"


def moisture_deviations(
    moisture: Decimal, day: int, drop: Decimal | None, parameters: DryingParameters
) -> list[Deviation]:
    """Los desvíos de una medición: su humedad, su día de secado y cuánto bajó la humedad desde la
    medición de la ventana de estancamiento (`None` si el secado todavía no la tiene)."""
    p = parameters
    found = []
    if drop is not None and drop < p.slow_stall_min_drop_pct:
        found.append(Deviation(SLOW_STALLED, NORMAL, str(drop), str(p.slow_stall_min_drop_pct)))
    if day >= p.slow_duration_day and moisture > p.slow_duration_moisture_pct:
        found.append(
            Deviation(SLOW_DURATION, NORMAL, str(moisture), str(p.slow_duration_moisture_pct))
        )
    if day <= p.accelerated_day and moisture < p.accelerated_moisture_pct:
        found.append(
            Deviation(ACCELERATED, NORMAL, str(moisture), str(p.accelerated_moisture_pct))
        )
    if p.near_target_min_pct <= moisture <= p.near_target_max_pct:
        target = f"{p.near_target_min_pct}-{p.near_target_max_pct}"
        found.append(Deviation(NEAR_TARGET, NORMAL, str(moisture), target))
    if moisture < p.overdried_moisture_pct:
        found.append(Deviation(OVERDRIED, CRITICAL, str(moisture), str(p.overdried_moisture_pct)))
    return found


def log_deviations(entry: DryingLogEntry) -> list[Deviation]:
    """Los desvíos de una bitácora guardada. Un fallo al calcularlos no impide guardarla: queda
    registrado y la bitácora sale sin desvíos."""
    try:
        process = entry.process
        parameters = drying_parameters(process.lot.harvest.plot.farm.producer_id)
        return moisture_deviations(
            entry.moisture_pct, entry.day_number, _drop(entry, parameters), parameters
        )
    except Exception as exc:
        log_unhandled_error(exc, where="los desvíos de una bitácora de secado")
        return []


def _drop(entry: DryingLogEntry, parameters: DryingParameters) -> Decimal | None:
    """Cuánto bajó la humedad desde la última medición hecha la ventana o más antes, en horas
    reales. Sin ninguna (el secado es más corto que la ventana), no se evalúa el estancamiento."""
    window = timedelta(hours=parameters.slow_stall_window_hours)
    earlier = (
        DryingLogEntry.objects.filter(
            process_id=entry.process_id, measured_at__lte=entry.measured_at - window
        )
        .exclude(pk=entry.pk)
        .order_by("-measured_at")
        .values_list("moisture_pct", flat=True)
        .first()
    )
    return None if earlier is None else earlier - entry.moisture_pct


def stale_deviation_kinds(entry: DryingLogEntry) -> list[str]:
    """Los desvíos que la bitácora ya no cumple, para retirar su aviso al corregirla."""
    current = {deviation.kind for deviation in log_deviations(entry)}
    return [kind for kind in DEVIATION_KINDS if kind not in current]


def drying_log_alerts(entry: DryingLogEntry) -> list[NotificationDraft]:
    """Un aviso por desvío para el responsable del secado y para quienes registran la bitácora en
    la finca del lote (el Productor entre ellos, por su rol)."""
    deviations = log_deviations(entry)
    if not deviations:
        return []
    process = entry.process
    lot = process.lot
    farm = lot.harvest.plot.farm
    recipients = FarmAccounts({farm.producer_id}, LOG_PERMISSION).on_farm(
        farm.producer_id, farm.pk
    )
    if process.responsible.is_active:
        recipients.add(process.responsible_id)
    return [
        NotificationDraft(
            recipient_id=recipient_id,
            kind=deviation.kind,
            severity=deviation.severity,
            condition_key=f"{entry.pk}:{deviation.kind}",
            # Cada desvío en su hilo: el de hoy reemplaza al de ayer del mismo lote, pero un
            # secado lento no oculta un sobresecado.
            thread_key=f"lot:{lot.pk}:{deviation.kind}",
            lot_id=lot.pk,
            drying_log_id=entry.pk,
            condition_at=entry.measured_at,
        )
        for deviation in deviations
        for recipient_id in sorted(recipients, key=str)
    ]
