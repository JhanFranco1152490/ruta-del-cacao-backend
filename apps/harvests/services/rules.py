"""Las reglas de una cosecha: lo que la ficha de la parcela, la fecha y el peso permiten."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from apps.common.assignable import assignable_person

from ..exceptions import (
    CollectorNotAvailable,
    HarvestInLot,
    InvalidHarvest,
    PlotNotCharacterized,
    VarietyNotInPlot,
)

ADD_PERMISSION = "harvests.add_harvest"
MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
# Una finca bien manejada da del orden de 1.000 a 2.000 kg de grano seco por hectárea al año
# (2.500 a 5.000 en baba), repartidos en muchas recolecciones. Este tope queda muy por encima de
# una recolección real y atrapa un error de digitación, como un cero de más.
MAX_GREEN_KG_PER_HECTARE = 2000


def characterization_of(plot):
    """La ficha de la parcela y sus siembras (con su variedad), o `PlotNotCharacterized` si no
    tiene ficha o no tiene siembras: no hay qué cosechar. La ficha se alcanza por la relación de
    la parcela, sin importar la app que la define."""
    try:
        characterization = plot.characterization
    except ObjectDoesNotExist:
        raise PlotNotCharacterized() from None
    plantings = list(characterization.plantings.select_related("variety"))
    if not plantings:
        raise PlotNotCharacterized()
    return characterization, plantings


def oldest_planting(plantings, variety_id):
    """La siembra más antigua de la variedad en la parcela, o `VarietyNotInPlot`."""
    of_variety = [planting for planting in plantings if planting.variety_id == variety_id]
    if not of_variety:
        raise VarietyNotInPlot()
    return min(of_variety, key=lambda planting: planting.planting_date)


def collector_for(actor, plot, collector_id):
    account = assignable_person(actor, plot, collector_id, ADD_PERMISSION)
    if account is None:
        raise CollectorNotAvailable()
    return account


def max_green_weight(plot) -> Decimal:
    return plot.area_hectares * MAX_GREEN_KG_PER_HECTARE


def check_date(harvest_date: date, planting) -> None:
    """No futura y no anterior a la siembra más antigua de la variedad (`planting`; sin ella, solo
    lo primero). La siembra se guarda el día 1 de su mes, así que una cosecha del mismo mes de la
    siembra no se rechaza."""
    if harvest_date > timezone.localdate():
        raise InvalidHarvest("harvest_date", "La fecha no puede ser futura.")
    if planting is not None and harvest_date < planting.planting_date:
        month = MONTHS[planting.planting_date.month - 1]
        raise InvalidHarvest(
            "harvest_date",
            f"La fecha es anterior a la siembra de {planting.variety.name} en esta parcela "
            f"({month} de {planting.planting_date.year}).",
        )


def check_weight(plot, green_weight_kg: Decimal) -> None:
    if green_weight_kg <= 0:
        raise InvalidHarvest("green_weight_kg", "El peso debe ser mayor a 0.")
    maximum = max_green_weight(plot)
    if green_weight_kg > maximum:
        raise InvalidHarvest(
            "green_weight_kg",
            f"El peso supera lo que puede dar una parcela de {plot.area_hectares.normalize():f} "
            f"ha en una recolección ({maximum.normalize():f} kg). Revisa la cifra.",
        )


def ensure_not_in_lot(harvest) -> None:
    """Una cosecha que forma un lote se congela: su peso es el del lote y su fecha forma parte de
    su código. El lote se alcanza por la relación inversa, sin importar la app que lo define."""
    if getattr(harvest, "lot", None) is not None:
        raise HarvestInLot()
