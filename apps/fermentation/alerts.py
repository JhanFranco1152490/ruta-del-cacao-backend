"""Las reglas de los volteos que comparten la pantalla de fermentación y los avisos de volteo
pendiente, y los desvíos de lo que mide cada volteo. Viven en un solo lugar para que lo que la
pantalla muestra como pendiente sea lo mismo que dispara un aviso.

El protocolo de campo voltea la masa a las 48 horas del inicio y después cada 24 horas; son los
valores de la línea base de los parámetros de poscosecha, que cada productor puede ajustar a su
región, igual que los rangos de temperatura y de pH.

El pH es el del grano, no el de la pulpa. El grano empieza casi neutro y su pH baja a medida que el
ácido de la pulpa entra en él, sobre todo entre el tercer y el cuarto día. Por eso un pH por debajo
del mínimo avisa en cualquier volteo, y uno por encima del máximo solo desde `PH_HIGH_AFTER`: antes
es lo normal.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Max

from apps.common.contracts.alerts import Deviation, NotificationDraft, deviation_drafts
from apps.common.contracts.postharvest_parameters import (
    FermentationParameters,
    fermentation_parameters,
)
from apps.common.contracts.schedulers import FarmAccounts
from apps.common.exceptions import log_unhandled_error

from .models import FermentationProcess, FermentationTurn

# Con cuánta anticipación se avisa que se acerca el primer volteo.
FIRST_TURN_WARNING = timedelta(hours=6)
# Desde cuándo un pH del grano por encima del máximo dice que la fermentación no avanza: el cuarto
# día, cuando el grano ya debería andar cerca de 4,75.
PH_HIGH_AFTER = timedelta(hours=96)

TURN_PERMISSION = "fermentation.log_turns"

FIRST_TURN_DUE = "fermentation_first_turn_due"
TURN_DUE = "fermentation_turn_due"
# Lo que queda resuelto cuando llega un volteo o termina la fermentación.
PENDING_KINDS = (FIRST_TURN_DUE, TURN_DUE)

TEMPERATURE_LOW = "fermentation_temperature_low"
TEMPERATURE_HIGH = "fermentation_temperature_high"
PH_LOW = "fermentation_ph_low"
PH_HIGH = "fermentation_ph_high"
DEVIATION_KINDS = (TEMPERATURE_LOW, TEMPERATURE_HIGH, PH_LOW, PH_HIGH)

# Ninguno es crítico: una temperatura o un pH fuera de rango hablan de una tendencia de días, que
# se corrige con el siguiente volteo.
NORMAL = "normal"


def next_turn_due_at(
    started_at: datetime, last_turned_at: datetime | None, parameters: FermentationParameters
) -> datetime:
    """Cuándo toca el siguiente volteo: las horas del primer volteo después del inicio si todavía
    no hay volteos, o las de los siguientes después del último (48 y 24 en la línea base). Es una
    guía: un volteo se registra a la hora en que se hizo."""
    if last_turned_at is None:
        return started_at + timedelta(hours=parameters.first_turn_hours)
    return last_turned_at + timedelta(hours=parameters.next_turn_hours)


def measurement_deviations(
    temperature: Decimal, ph: Decimal, elapsed: timedelta, parameters: FermentationParameters
) -> list[Deviation]:
    """Los desvíos de lo que midió un volteo hecho `elapsed` después del inicio. Los límites son
    inclusivos: 40,0 °C y pH 5,50 están dentro del rango."""
    p = parameters
    found = []
    if temperature < p.temperature_min_c:
        found.append(
            Deviation(TEMPERATURE_LOW, NORMAL, str(temperature), str(p.temperature_min_c))
        )
    elif temperature > p.temperature_max_c:
        found.append(
            Deviation(TEMPERATURE_HIGH, NORMAL, str(temperature), str(p.temperature_max_c))
        )
    if ph < p.ph_min:
        found.append(Deviation(PH_LOW, NORMAL, str(ph), str(p.ph_min)))
    elif ph > p.ph_max and elapsed >= PH_HIGH_AFTER:
        found.append(Deviation(PH_HIGH, NORMAL, str(ph), str(p.ph_max)))
    return found


def turn_deviations(turn: FermentationTurn) -> list[Deviation]:
    """Los desvíos de un volteo guardado. Un fallo al calcularlos no impide guardarlo: queda
    registrado y el volteo sale sin desvíos."""
    return _evaluated(turn) or []


def _evaluated(turn: FermentationTurn) -> list[Deviation] | None:
    """Los desvíos, o `None` si no se pudieron calcular: no es lo mismo que no tener ninguno."""
    try:
        process = turn.process
        parameters = fermentation_parameters(process.lot.harvest.plot.farm.producer_id)
        return measurement_deviations(
            turn.temperature_c, turn.ph, turn.turned_at - process.started_at, parameters
        )
    except Exception as exc:
        log_unhandled_error(exc, where="los desvíos de un volteo")
        return None


def stale_deviation_kinds(turn: FermentationTurn) -> list[str]:
    """Los desvíos que el volteo ya no cumple, para retirar su aviso al corregirlo. Si no se
    pudieron calcular, ninguno: retirarlos todos borraría avisos que pueden seguir siendo ciertos.
    """
    deviations = _evaluated(turn)
    if deviations is None:
        return []
    current = {deviation.kind for deviation in deviations}
    return [kind for kind in DEVIATION_KINDS if kind not in current]


def turn_alerts(turn: FermentationTurn) -> list[NotificationDraft]:
    """Un aviso por desvío para el responsable de la fermentación y para quienes registran volteos
    en la finca del lote (el Productor entre ellos, por su rol)."""
    deviations = turn_deviations(turn)
    if not deviations:
        return []
    process = turn.process
    farm = process.lot.harvest.plot.farm
    recipients = FarmAccounts({farm.producer_id}, TURN_PERMISSION).on_farm_with(
        farm.producer_id, farm.pk, process.responsible
    )
    return deviation_drafts(
        deviations,
        recipients,
        lot_id=process.lot_id,
        condition_at=turn.turned_at,
        fermentation_turn_id=turn.pk,
    )


def evaluate(today, now) -> list[NotificationDraft]:
    """Los volteos pendientes de las fermentaciones en curso, en la evaluación de cada hora.

    Como una actividad: mientras no ha pasado nada, se le recuerda solo al responsable que se
    acerca el primer volteo; cuando la hora de un volteo llega sin que se registre, se le avisa
    también a quienes voltean en la finca (el Productor entre ellos). El número del volteo va en la
    clave, así que cada uno avisa una sola vez."""
    processes = list(
        FermentationProcess.objects.filter(ended_at__isnull=True)
        .select_related("lot__harvest__plot__farm", "responsible")
        .annotate(turn_count=Count("turns"), last_turned_at=Max("turns__turned_at"))
    )
    producer_ids = {process.lot.harvest.plot.farm.producer_id for process in processes}
    parameters = {
        producer_id: fermentation_parameters(producer_id) for producer_id in producer_ids
    }
    accounts = FarmAccounts(producer_ids, TURN_PERMISSION)
    found = []
    for process in processes:
        farm = process.lot.harvest.plot.farm
        due_at = next_turn_due_at(
            process.started_at, process.last_turned_at, parameters[farm.producer_id]
        )
        if now >= due_at:
            number = process.turn_count + 1
            recipients = accounts.on_farm_with(farm.producer_id, farm.pk, process.responsible)
            key = f"{process.lot_id}:turn:{number}"
            found.extend(_pending(process, TURN_DUE, key, due_at, recipients))
        elif process.turn_count == 0 and due_at - now <= FIRST_TURN_WARNING:
            if process.responsible.is_active:
                key = f"{process.lot_id}:first_turn"
                found.extend(
                    _pending(process, FIRST_TURN_DUE, key, due_at, {process.responsible_id})
                )
    return found


def _pending(process, kind, key, due_at, recipient_ids) -> list[NotificationDraft]:
    return [
        NotificationDraft(
            recipient_id=recipient_id,
            kind=kind,
            condition_key=key,
            # Un solo hilo por lote: el volteo pendiente reemplaza al recordatorio, y el de hoy al
            # de ayer.
            thread_key=f"lot:{process.lot_id}",
            lot_id=process.lot_id,
            condition_at=due_at,
        )
        for recipient_id in sorted(recipient_ids, key=str)
    ]
