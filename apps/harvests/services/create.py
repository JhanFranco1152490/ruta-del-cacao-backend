from django.db import transaction

from apps.common.db import save_translating_unique
from apps.common.ownership import owns, reaches_farm

from ..exceptions import HarvestIdConflict
from ..models import Harvest, HarvestAuditEvent
from . import queries, rules
from .audit import harvest_values, record_harvest_event

ID_CONSTRAINT = "harvests_harvest_pkey"


@transaction.atomic
def create_harvest(actor, data: dict) -> tuple[Harvest, bool]:
    """Registra una cosecha en una parcela del productor de la sesión. Devuelve `(cosecha,
    creada)`.

    El cliente envía el `id` que generó: reenviar el mismo `id` con los mismos datos devuelve la
    cosecha ya creada (`creada=False`), de modo que reintentar un envío cortado nunca duplica. Un
    reenvío no se vuelve a validar: la cosecha pudo capturarse horas antes y lo que la ficha diga
    hoy ya no cambia lo que se recogió.

    Una parcela o una finca inactivas no impiden registrar: el cacao ya se recogió y el dato no
    se pierde.
    """
    harvest_id = data.get("id")
    if harvest_id is not None and (existing := _existing(harvest_id)) is not None:
        return _resent(existing, actor, data), False

    plot = queries.lock_plot(actor, data["plot_id"])
    # Con la finca bloqueada, un envío del mismo registro que llegó a la vez ya terminó: si la
    # creó, se responde como un reenvío.
    if harvest_id is not None and (existing := _existing(harvest_id)) is not None:
        return _resent(existing, actor, data), False

    characterization, plantings = rules.characterization_of(plot)
    planting = rules.oldest_planting(plantings, data["variety_id"])
    collector = rules.collector_for(actor, plot, data["collector_id"])
    rules.check_date(data["harvest_date"], planting)
    rules.check_weight(plot, data["green_weight_kg"])

    harvest = Harvest(
        plot=plot,
        harvest_date=data["harvest_date"],
        green_weight_kg=data["green_weight_kg"],
        variety_id=data["variety_id"],
        collector=collector,
        characterization_version=characterization.version,
        registered_by=actor,
        captured_at=data.get("captured_at"),
    )
    if harvest_id is not None:
        harvest.pk = harvest_id
    # El mismo `id` en una parcela de otra finca no pasa por el mismo bloqueo: el choque llega
    # como clave primaria repetida.
    existing = save_translating_unique(
        lambda: harvest.save(force_insert=True),
        constraint=ID_CONSTRAINT,
        duplicate=HarvestIdConflict,
        find_existing=lambda: _existing(harvest.pk) if harvest_id is not None else None,
    )
    if existing is not None:
        return _resent(existing, actor, data), False
    record_harvest_event(
        harvest=harvest,
        actor=actor,
        action=HarvestAuditEvent.Action.CREATED,
        before={},
        after=harvest_values(harvest),
    )
    return harvest, True


def _existing(harvest_id) -> Harvest | None:
    return Harvest.objects.select_related("plot__farm").filter(pk=harvest_id).first()


def _resent(existing: Harvest, actor, data: dict) -> Harvest:
    farm = existing.plot.farm
    if not (owns(actor, farm.producer_id) and reaches_farm(actor, farm.pk)):
        raise HarvestIdConflict()
    sent = {
        "plot_id": str(data["plot_id"]),
        "harvest_date": data["harvest_date"],
        "green_weight_kg": data["green_weight_kg"],
        "variety_id": str(data["variety_id"]),
        "collector_id": str(data["collector_id"]),
    }
    stored = {
        "plot_id": str(existing.plot_id),
        "harvest_date": existing.harvest_date,
        "green_weight_kg": existing.green_weight_kg,
        "variety_id": str(existing.variety_id),
        "collector_id": str(existing.collector_id),
    }
    if sent != stored:
        raise HarvestIdConflict()
    return existing
