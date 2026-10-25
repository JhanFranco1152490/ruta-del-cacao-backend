"""La fermentación de los lotes de La Esperanza: uno ya fermentado, uno fermentando con el volteo
siguiente pendiente y uno recién conformado para iniciar en vivo. Todo por los servicios de la
fermentación, que aceptan horas del pasado (no anteriores a la cosecha), así que no hace falta
correr nada de fecha.

Se hace una sola vez: si la finca ya tiene alguna fermentación, no se toca, porque pudo cambiar
desde la aplicación.
"""

import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import User
from apps.activities.state import today_in_bogota
from apps.facilities.models import PostharvestFacility
from apps.farms.models import Farm
from apps.fermentation.models import FermentationProcess
from apps.fermentation.services.finish import finish_fermentation
from apps.fermentation.services.start import start_fermentation
from apps.fermentation.services.turns import record_turn
from apps.harvests.services.create import create_harvest
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.lots.services.create import create_lot
from apps.plots.models import Plot

# Cuántos kilos trae el lote que se inicia en vivo: cabe en cualquiera de los dos cajones.
LIVE_LOT_KG = Decimal("200")


def seed_fermentations(owner: User, foreman: User, plot: Plot) -> list[str]:
    farm = plot.farm
    if FermentationProcess.objects.filter(lot__harvest__plot__farm=farm).exists():
        return []
    # Los dos lotes que deja la cosecha de demostración, del más antiguo al más reciente.
    oldest, newest = Lot.objects.filter(
        harvest__plot__farm=farm, status=LotStatus.GENERATED
    ).order_by("harvest__harvest_date")[:2]
    big_box, small_box = _boxes(farm)
    _fermented(owner, foreman, oldest, big_box)
    _fermenting(foreman, newest, small_box)
    _live_lot(owner, foreman, plot)
    return [
        f"Fermentación: {oldest.code} fermentado, {newest.code} fermentando con el volteo "
        f"pendiente y un lote listo para iniciar en {big_box.name}"
    ]


def _boxes(farm: Farm) -> tuple[PostharvestFacility, PostharvestFacility]:
    """Los dos cajones de la finca, el más grande primero: el lote fermentado lo deja libre para la
    demostración en vivo."""
    boxes = PostharvestFacility.objects.filter(
        farm=farm, facility_type="fermentation_box", is_active=True
    ).order_by("-capacity_kg", "name_normalized")
    return boxes[0], boxes[1]


def _fermented(owner: User, foreman: User, lot: Lot, box: PostharvestFacility) -> None:
    """Cinco días en el cajón, con los tres volteos del protocolo, y finalizada por el
    Productor."""
    day = lot.harvest.harvest_date + timedelta(days=1)
    started_at = timezone.make_aware(datetime.combine(day, time(7, 0)))
    _start(foreman, lot, box, started_at)
    temperatures = ("44.5", "47.0", "45.5")
    ph_values = ("4.90", "4.70", "5.10")
    for hours, temperature, ph in zip((48, 72, 96), temperatures, ph_values, strict=True):
        _turn(foreman, lot, started_at + timedelta(hours=hours), temperature, ph)
    finish_fermentation(
        owner,
        lot.pk,
        1,
        {
            "ended_at": started_at + timedelta(hours=118),
            "notes": "Grano marrón al corte y olor a vinagre: listo para secar.",
        },
    )


def _fermenting(foreman: User, lot: Lot, box: PostharvestFacility) -> None:
    """Desde hace cien horas, con los volteos de las 48 y las 72: el de las 96 está pendiente."""
    started_at = (timezone.now() - timedelta(hours=100)).replace(second=0, microsecond=0)
    _start(foreman, lot, box, started_at)
    _turn(foreman, lot, started_at + timedelta(hours=48), "43.0", "4.95")
    _turn(foreman, lot, started_at + timedelta(hours=72), "46.5", "4.75")


def _live_lot(owner: User, foreman: User, plot: Plot) -> None:
    """Una cosecha de hace tres días ya conformada en lote, para iniciar su fermentación en
    vivo."""
    variety = plot.characterization.plantings.order_by("planting_date").first().variety
    harvest, _ = create_harvest(
        owner,
        {
            "plot_id": plot.pk,
            "harvest_date": today_in_bogota() - timedelta(days=3),
            "green_weight_kg": LIVE_LOT_KG,
            "variety_id": variety.pk,
            "collector_id": foreman.pk,
            "captured_at": None,
        },
    )
    create_lot(owner, {"harvest_id": harvest.pk})


def _start(foreman: User, lot: Lot, box: PostharvestFacility, started_at) -> None:
    start_fermentation(
        foreman,
        {
            "lot_id": lot.pk,
            "facility_id": box.pk,
            "started_at": started_at,
            "responsible_id": foreman.pk,
        },
    )


def _turn(foreman: User, lot: Lot, turned_at, temperature: str, ph: str) -> None:
    record_turn(
        foreman,
        lot.pk,
        {
            "id": uuid.uuid4(),
            "turned_at": turned_at,
            "temperature_c": Decimal(temperature),
            "ph": Decimal(ph),
        },
    )
