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
from apps.fermentation.services.start import start_fermentation
from apps.fermentation.services.turns import record_turn
from apps.harvests.services.create import create_harvest
from apps.lots.models import Lot
from apps.lots.services.create import create_lot
from apps.plots.models import Plot

DRIED_LOT_KG = Decimal("300")
DRYING_LOT_KG = Decimal("250")
# El rendimiento típico del cacao: el 38 % del peso en verde.
DRIED_WEIGHT_KG = Decimal("114.0")


def seed_dryings(owner: User, foreman: User, plot: Plot) -> list[str]:
    farm = plot.farm
    if DryingProcess.objects.filter(lot__harvest__plot__farm=farm).exists():
        return []
    box = _free_box(farm)
    first_dryer, second_dryer = _dryers(farm)
    if box is None or first_dryer is None or second_dryer is None:
        return []
    dried = _fermented_lot(owner, foreman, plot, box, harvest_days_ago=14, weight=DRIED_LOT_KG)
    _dried(owner, foreman, dried, first_dryer)
    drying = _fermented_lot(owner, foreman, plot, box, harvest_days_ago=9, weight=DRYING_LOT_KG)
    _drying(foreman, drying, second_dryer)
    return [
        f"Secado: {dried.code} seco con su rendimiento, {drying.code} secando en "
        f"{second_dryer.name} sin la bitácora de hoy, y {first_dryer.name} libre para iniciar"
    ]


def _free_box(farm) -> PostharvestFacility | None:
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


def _at(days_ago: int, hour: int):
    day = today_in_bogota() - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


def _fermented_lot(owner, foreman, plot, box, *, harvest_days_ago: int, weight) -> Lot:
    """Una cosecha conformada en lote y fermentada cinco días en el cajón, con los volteos del
    protocolo: queda Fermentada la mañana del sexto día."""
    variety = plot.characterization.plantings.order_by("planting_date").first().variety
    harvest, _ = create_harvest(
        owner,
        {
            "plot_id": plot.pk,
            "harvest_date": today_in_bogota() - timedelta(days=harvest_days_ago),
            "green_weight_kg": weight,
            "variety_id": variety.pk,
            "collector_id": foreman.pk,
            "captured_at": None,
        },
    )
    lot, _ = create_lot(owner, {"harvest_id": harvest.pk})
    started_at = _at(harvest_days_ago - 1, 7)
    start_fermentation(
        foreman,
        {
            "lot_id": lot.pk,
            "facility_id": box.pk,
            "started_at": started_at,
            "responsible_id": foreman.pk,
        },
    )
    for hours in (48, 72, 96):
        record_turn(
            foreman,
            lot.pk,
            {
                "id": uuid.uuid4(),
                "turned_at": started_at + timedelta(hours=hours),
                "temperature_c": Decimal("45.5"),
                "ph": Decimal("4.85"),
            },
        )
    finish_fermentation(
        owner, lot.pk, 1, {"ended_at": started_at + timedelta(hours=118), "notes": ""}
    )
    return Lot.objects.get(pk=lot.pk)


def _start(foreman, lot, dryer, started_at) -> None:
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


def _log(foreman, lot, measured_at, moisture, sun, *, weather="sunny", shade=None) -> None:
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
    started_at = _at(8, 14)
    _start(foreman, lot, dryer, started_at)
    readings = (("52.0", "3.0"), ("38.0", "8.0"), ("22.0", "7.0"), ("12.0", "9.0"), ("7.2", "6.0"))
    for day, (moisture, sun) in enumerate(readings):
        hour = 17 if day == 0 else 16
        _log(foreman, lot, _at(8 - day, hour), moisture, sun)
    finish_drying(
        owner,
        lot.pk,
        1,
        {
            "ended_at": _at(4, 18),
            "final_moisture_pct": Decimal("7.0"),
            "dry_weight_kg": DRIED_WEIGHT_KG,
        },
    )


def _drying(foreman, lot, dryer) -> None:
    """Desde hace tres días a las 14:00, con la bitácora del día 1 y del día 2 (lluvioso, sin sol):
    la de hoy está pendiente."""
    _start(foreman, lot, dryer, _at(3, 14))
    _log(foreman, lot, _at(3, 17), "54.0", "3.0")
    _log(foreman, lot, _at(2, 16), "46.0", "0.0", weather="rainy", shade="9.0")
