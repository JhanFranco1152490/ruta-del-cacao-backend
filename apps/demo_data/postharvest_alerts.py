"""Los lotes de La Esperanza que muestran los avisos de poscosecha.

La fermentación y el secado de la semilla ya dejan dos: el volteo pendiente (el lote que fermenta)
y la bitácora pendiente (el que seca en M-02). Aquí se suman, cada uno en su cajón o su marquesina:

- en C-03, una fermentación de hace 43 horas sin volteos: el recordatorio del primer volteo;
- en C-04, una de hace 110 horas con un volteo frío a las 48 y uno con el pH del grano alto a las
  98: temperatura por debajo del rango y fermentación que no avanza;
- en M-03, un secado de seis días que llega a 8,1 %: próximo a la meta.

Los avisos de desvío los crean los servicios al registrar; los pendientes, la evaluación que corre
al terminar la semilla. Cada lote se crea una sola vez: si su cajón o su marquesina ya tuvo un
proceso, no se toca. Lo que sí se repite cada vez es dejar sin la bitácora de hoy el lote de M-02,
para registrar en vivo la del sobresecado.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.activities.state import today_in_bogota
from apps.drying.models import DryingLogEntry, DryingProcess
from apps.drying.services.logs import delete_log
from apps.facilities.models import PostharvestFacility
from apps.fermentation.models import FermentationProcess
from apps.plots.models import Plot

from .catalog import DEVIATIONS_BOX, LIVE_LOG_DRYER, NEAR_TARGET_DRYER, REMINDER_BOX
from .drying import at_day, fermented_lot, free_box, log_day, start_in_dryer
from .postharvest import harvested_lot, start_in_box, turn_at

ALERT_LOT_KG = Decimal("150")


def seed_postharvest_alerts(owner: User, foreman: User, plot: Plot) -> list[str]:
    farm = plot.farm
    notes = []
    now = timezone.now().replace(second=0, microsecond=0)
    reminder_box = _facility(farm, REMINDER_BOX)
    if reminder_box is not None and not _fermented_in(reminder_box):
        lot = harvested_lot(owner, foreman, plot, days_ago=4, weight=ALERT_LOT_KG)
        start_in_box(foreman, lot, reminder_box, now - timedelta(hours=43))
        notes.append(f"Aviso de primer volteo: {lot.code} en {reminder_box.name}")
    deviations_box = _facility(farm, DEVIATIONS_BOX)
    if deviations_box is not None and not _fermented_in(deviations_box):
        lot = _off_range_fermentation(owner, foreman, plot, deviations_box, now)
        notes.append(f"Avisos de temperatura y pH: {lot.code} en {deviations_box.name}")
    near_target_dryer = _facility(farm, NEAR_TARGET_DRYER)
    box = free_box(farm)
    if near_target_dryer is not None and box is not None and not _dried_in(near_target_dryer):
        lot = _near_target_drying(owner, foreman, plot, box, near_target_dryer)
        notes.append(f"Aviso de próximo a meta: {lot.code} en {near_target_dryer.name}")
    notes += _ready_for_the_live_log(owner, farm)
    return notes


def _facility(farm, name) -> PostharvestFacility | None:
    return PostharvestFacility.objects.filter(farm=farm, name__iexact=name).first()


def _fermented_in(box) -> bool:
    return FermentationProcess.objects.filter(facility=box).exists()


def _dried_in(dryer) -> bool:
    return DryingProcess.objects.filter(facility=dryer).exists()


def _off_range_fermentation(owner, foreman, plot, box, now):
    """Fermentando desde hace 110 horas. El volteo de las 48 salió frío (37,5 °C) y el de las 98
    tiene el pH del grano todavía en 6,10, cuando al cuarto día ya debería andar cerca de 4,75. El
    siguiente toca a las 122 horas: no queda ningún volteo pendiente."""
    lot = harvested_lot(owner, foreman, plot, days_ago=6, weight=ALERT_LOT_KG)
    started_at = now - timedelta(hours=110)
    start_in_box(foreman, lot, box, started_at)
    turn_at(foreman, lot, started_at + timedelta(hours=48), "37.5", "6.40")
    turn_at(foreman, lot, started_at + timedelta(hours=72), "44.0", "5.90")
    turn_at(foreman, lot, started_at + timedelta(hours=98), "46.0", "6.10")
    return lot


def _near_target_drying(owner, foreman, plot, box, dryer):
    """Fermentado hace dos semanas y secando desde hace cinco días a las 14:00, con la humedad
    bajando hasta 8,1 % el día 4. Sin la bitácora de ayer ni la de hoy: también queda pendiente."""
    lot = fermented_lot(owner, foreman, plot, box, harvest_days_ago=20, weight=ALERT_LOT_KG)
    start_in_dryer(foreman, lot, dryer, at_day(5, 14))
    log_day(foreman, lot, at_day(5, 17), "52.0", "3.0")
    log_day(foreman, lot, at_day(4, 16), "35.0", "8.0")
    log_day(foreman, lot, at_day(3, 16), "18.0", "7.0")
    log_day(foreman, lot, at_day(2, 16), "8.1", "6.0")
    return lot


def _ready_for_the_live_log(owner, farm) -> list[str]:
    """Deja sin la bitácora de hoy el lote que seca en M-02, por el servicio y con su historial:
    en la demostración se registra la de hoy con 5,8 % y se ve el sobresecado."""
    today = DryingLogEntry.objects.filter(
        process__facility__farm=farm,
        process__facility__name__iexact=LIVE_LOG_DRYER,
        process__ended_at__isnull=True,
        log_date=today_in_bogota(),
    ).select_related("process")
    notes = []
    for entry in today:
        delete_log(owner, entry.process.lot_id, entry.pk, entry.version)
        notes.append(f"Bitácora de hoy en {LIVE_LOG_DRYER}: eliminada para la demostración")
    return notes
