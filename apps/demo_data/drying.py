"""El secado de los lotes de La Esperanza: uno ya seco con su rendimiento y uno secando desde hace
tres días, sin la bitácora de hoy. El lote que la fermentación deja Fermentado queda para iniciar
su secado en vivo, en M-01.

Los dos lotes salen de cosechas nuevas, fermentadas por los servicios de la fermentación en el
cajón grande, que vuelve a quedar libre. Fermentación y secado aceptan horas del pasado, así que no
hace falta correr nada de fecha.

Se hace una sola vez: si la finca ya tiene algún secado, no se toca, porque pudo cambiar desde la
aplicación.
"""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.activities.state import today_in_bogota
from apps.drying.models import DryingProcess
from apps.drying.services.finish import finish_drying
from apps.drying.services.logs import record_log
from apps.drying.services.start import start_drying
from apps.facilities.models import PostharvestFacility
from apps.fermentation.services.finish import finish_fermentation
from apps.lots.models import Lot
from apps.plots.models import Plot

from .postharvest import harvested_lot, start_in_box, turn_at

DRIED_LOT_KG = Decimal("300")
DRYING_LOT_KG = Decimal("250")
# El rendimiento típico del cacao: el 38 % del peso en verde.
DRIED_WEIGHT_KG = Decimal("114.0")


def seed_dryings(owner: User, foreman: User, plot: Plot) -> list[str]:
    farm = plot.farm
    if DryingProcess.objects.filter(lot__harvest__plot__farm=farm).exists():
        return []
    box = free_box(farm)
    first_dryer, second_dryer = _dryers(farm)
    if box is None or first_dryer is None or second_dryer is None:
        return []
    dried = fermented_lot(owner, foreman, plot, box, harvest_days_ago=14, weight=DRIED_LOT_KG)
    _dried(owner, foreman, dried, first_dryer)
    drying = fermented_lot(owner, foreman, plot, box, harvest_days_ago=9, weight=DRYING_LOT_KG)
    _drying(foreman, drying, second_dryer)
    return [
        f"Secado: {dried.code} seco con su rendimiento, {drying.code} secando en "
        f"{second_dryer.name} sin la bitácora de hoy, y {first_dryer.name} libre para iniciar"
    ]


def free_box(farm) -> PostharvestFacility | None:
    """El cajón más grande que esté libre: se fermenta en él y vuelve a quedar libre."""
    return (
        PostharvestFacility.objects.filter(
            farm=farm, facility_type="fermentation_box", is_active=True, current_lot__isnull=True
        )
        .order_by("-capacity_kg", "name_normalized")
        .first()
    )


def _dryers(farm) -> tuple[PostharvestFacility | None, PostharvestFacility | None]:
    dryers = list(
        PostharvestFacility.objects.filter(
            farm=farm, facility_type="solar_dryer", is_active=True, current_lot__isnull=True
        ).order_by("name_normalized")[:2]
    )
    return (dryers + [None, None])[0], (dryers + [None, None])[1]


def at_day(days_ago: int, hour: int):
    day = today_in_bogota() - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


def fermented_lot(owner, foreman, plot, box, *, harvest_days_ago: int, weight) -> Lot:
    """Una cosecha conformada en lote y fermentada cinco días en el cajón, con los volteos del
    protocolo: queda Fermentada la mañana del sexto día."""
    lot = harvested_lot(owner, foreman, plot, days_ago=harvest_days_ago, weight=weight)
    started_at = at_day(harvest_days_ago - 1, 7)
    start_in_box(foreman, lot, box, started_at)
    for hours in (48, 72, 96):
        turn_at(foreman, lot, started_at + timedelta(hours=hours), "45.5", "4.85")
    finish_fermentation(
        owner, lot.pk, 1, {"ended_at": started_at + timedelta(hours=118), "notes": ""}
    )
    return Lot.objects.get(pk=lot.pk)


def start_in_dryer(foreman, lot, dryer, started_at) -> None:
    start_drying(
        foreman,
        {
            "lot_id": lot.pk,
            "facility_id": dryer.pk,
            "started_at": started_at,
            "entry_moisture_pct": Decimal("58.0"),
            "responsible_id": foreman.pk,
        },
    )


def log_day(foreman, lot, measured_at, moisture, sun, *, weather="sunny", shade=None) -> None:
    turns = 0 if sun == "0.0" else 3
    record_log(
        foreman,
        lot.pk,
        {
            "id": uuid.uuid4(),
            "measured_at": measured_at,
            "moisture_pct": Decimal(moisture),
            "sun_hours": Decimal(sun),
            "shade_hours": Decimal(shade) if shade else None,
            "turn_count": turns,
            "turn_frequency_hours": Decimal("2.0") if turns else None,
            "weather": weather,
        },
    )


def _dried(owner, foreman, lot, dryer) -> None:
    """Cinco días en M-01 desde las 14:00 del día en que terminó la fermentación, con la humedad
    bajando hasta la meta, y finalizado por el Productor."""
    started_at = at_day(8, 14)
    start_in_dryer(foreman, lot, dryer, started_at)
    readings = (("52.0", "3.0"), ("38.0", "8.0"), ("22.0", "7.0"), ("12.0", "9.0"), ("7.2", "6.0"))
    for day, (moisture, sun) in enumerate(readings):
        hour = 17 if day == 0 else 16
        log_day(foreman, lot, at_day(8 - day, hour), moisture, sun)
    finish_drying(
        owner,
        lot.pk,
        1,
        {
            "ended_at": at_day(4, 18),
            "final_moisture_pct": Decimal("7.0"),
            "dry_weight_kg": DRIED_WEIGHT_KG,
        },
    )


def _drying(foreman, lot, dryer) -> None:
    """Desde hace tres días a las 14:00, con la bitácora del día 1 y del día 2 (lluvioso, sin sol):
    la de hoy está pendiente."""
    start_in_dryer(foreman, lot, dryer, at_day(3, 14))
    log_day(foreman, lot, at_day(3, 17), "54.0", "3.0")
    log_day(foreman, lot, at_day(2, 16), "46.0", "0.0", weather="rainy", shade="9.0")
