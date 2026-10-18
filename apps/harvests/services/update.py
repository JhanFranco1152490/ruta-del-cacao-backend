from django.db import transaction

from apps.common.versioning import check_expected_version, save_next_version

from ..exceptions import PlotNotCharacterized, StaleHarvestVersion, VarietyNotInPlot
from ..models import Harvest, HarvestAuditEvent
from . import queries, rules
from .audit import harvest_values, record_harvest_event

# Lo que una corrección puede cambiar. La parcela no está: si se eligió mal, se elimina la cosecha
# y se registra de nuevo.
EDITABLE_FIELDS = ("harvest_date", "green_weight_kg", "variety_id", "collector_id")


@transaction.atomic
def update_harvest(actor, harvest_id, expected_version: int, data: dict) -> Harvest:
    """Corrige una cosecha que todavía no forma un lote. `data` trae solo los campos que se quieren
    cambiar. Cada regla se revisa solo si lo que mira cambia: una variedad que la ficha ya no
    tiene, o un recolector que cambió de finca, no impiden corregir el peso."""
    harvest = queries.lock_harvest(actor, harvest_id)
    rules.ensure_not_in_lot(harvest)
    if check_expected_version(
        harvest,
        expected_version,
        stale=lambda: StaleHarvestVersion(harvest),
        already_applied=lambda: not _changed(harvest, data),
    ):
        return harvest

    changed = _changed(harvest, data)
    if not changed:
        return harvest
    before = harvest_values(harvest)
    plot = harvest.plot
    planting = None
    update_fields = []

    if "variety_id" in changed:
        characterization, plantings = rules.characterization_of(plot)
        planting = rules.oldest_planting(plantings, data["variety_id"])
        # La ficha de la que sale la variedad nueva es la vigente: la cosecha guarda su versión.
        harvest.variety_id = data["variety_id"]
        harvest.characterization_version = characterization.version
        update_fields += ["variety", "characterization_version"]
    elif "harvest_date" in changed:
        planting = _current_planting(harvest)
    if "collector_id" in changed:
        harvest.collector = rules.collector_for(actor, plot, data["collector_id"])
        update_fields.append("collector")
    if "harvest_date" in changed:
        harvest.harvest_date = data["harvest_date"]
        update_fields.append("harvest_date")
    if "green_weight_kg" in changed:
        harvest.green_weight_kg = data["green_weight_kg"]
        update_fields.append("green_weight_kg")

    if "harvest_date" in changed or "variety_id" in changed:
        rules.check_date(harvest.harvest_date, planting)
    if "green_weight_kg" in changed:
        rules.check_weight(plot, harvest.green_weight_kg)

    save_next_version(harvest, update_fields)
    record_harvest_event(
        harvest=harvest,
        actor=actor,
        action=HarvestAuditEvent.Action.UPDATED,
        before=before,
        after=harvest_values(harvest),
    )
    return harvest


def _changed(harvest: Harvest, data: dict) -> list[str]:
    return [
        name for name in EDITABLE_FIELDS if name in data and getattr(harvest, name) != data[name]
    ]


def _current_planting(harvest: Harvest):
    """La siembra más antigua de la variedad de la cosecha, para revisar la fecha nueva, o `None`
    si la ficha ya no la tiene: entonces solo se exige que la fecha no sea futura."""
    try:
        _, plantings = rules.characterization_of(harvest.plot)
        return rules.oldest_planting(plantings, harvest.variety_id)
    except (PlotNotCharacterized, VarietyNotInPlot):
        return None
