from django.db import transaction

from apps.common.db import save_translating_unique
from apps.common.ownership import owns, reaches_farm

from ..code import build_lot_code
from ..exceptions import HarvestAlreadyInLot, LotIdConflict
from ..models import Lot, LotAuditEvent, LotCodeSequence
from . import queries
from .audit import record_lot_event

ID_CONSTRAINT = "lots_lot_pkey"


@transaction.atomic
def create_lot(actor, data: dict) -> tuple[Lot, bool]:
    """Conforma el lote de una cosecha y le asigna su código. Devuelve `(lote, creado)`.

    El cliente envía el `id` que generó: reenviar el mismo `id` para la misma cosecha devuelve el
    lote ya creado (`creado=False`), de modo que reintentar un envío cortado nunca crea otro.
    El código lo asigna el servidor, con la finca bloqueada: dos lotes de la misma parcela y el
    mismo día reciben consecutivos distintos, y dos peticiones sobre la misma cosecha dejan un
    solo lote.

    Una parcela o una finca inactivas no impiden conformar el lote de una cosecha ya registrada.
    """
    lot_id = data.get("id")
    if lot_id is not None and (existing := _existing(lot_id)) is not None:
        return _resent(existing, actor, data), False

    harvest = queries.lock_harvest(actor, data["harvest_id"])
    # Con la finca bloqueada, un envío que llegó a la vez ya terminó: si creó el lote, se responde
    # como un reenvío.
    if lot_id is not None and (existing := _existing(lot_id)) is not None:
        return _resent(existing, actor, data), False
    current = Lot.objects.filter(harvest_id=harvest.pk).first()
    if current is not None:
        raise HarvestAlreadyInLot(current)

    plot = harvest.plot
    sequence = _next_sequence(plot, harvest.harvest_date)
    lot = Lot(
        harvest=harvest,
        code=build_lot_code(
            plot.farm.producer.member_code,
            plot.farm.number,
            plot.number,
            harvest.harvest_date,
            sequence,
        ),
        created_by=actor,
    )
    if lot_id is not None:
        lot.pk = lot_id
    # El mismo `id` en una cosecha de otra finca no pasa por el mismo bloqueo: el choque llega como
    # clave primaria repetida.
    existing = save_translating_unique(
        lambda: lot.save(force_insert=True),
        constraint=ID_CONSTRAINT,
        duplicate=LotIdConflict,
        find_existing=lambda: _existing(lot.pk) if lot_id is not None else None,
    )
    if existing is not None:
        return _resent(existing, actor, data), False
    record_lot_event(
        lot=lot,
        actor=actor,
        action=LotAuditEvent.Action.CREATED,
        before={},
        after={"status": lot.status},
    )
    return lot, True


def _next_sequence(plot, harvest_date) -> int:
    """El siguiente consecutivo de la parcela en ese día de cosecha. La fila se bloquea y el
    número no baja al eliminar un lote, así que nunca se reutiliza."""
    sequence, _ = LotCodeSequence.objects.select_for_update().get_or_create(
        plot=plot, harvest_date=harvest_date
    )
    sequence.last_value += 1
    sequence.save(update_fields=["last_value"])
    return sequence.last_value


def _existing(lot_id) -> Lot | None:
    return Lot.objects.select_related("harvest__plot__farm__producer").filter(pk=lot_id).first()


def _resent(existing: Lot, actor, data: dict) -> Lot:
    farm = existing.harvest.plot.farm
    if not (owns(actor, farm.producer_id) and reaches_farm(actor, farm.pk)):
        raise LotIdConflict()
    if str(existing.harvest_id) != str(data["harvest_id"]):
        raise LotIdConflict()
    return existing
