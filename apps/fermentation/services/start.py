"""Iniciar la fermentación de un lote en un cajón, y las reglas del inicio que comparte con
corregirlo."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.common.contracts.assignable import assignable_person
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import (
    FacilityNotFound,
    InvalidFermentation,
    LotExceedsCapacity,
    LotInvalidStatus,
    LotNotFound,
    ResponsibleNotAvailable,
    ResponsibleNotFound,
)
from ..models import FermentationProcess, FermentationProcessAuditEvent
from .audit import record_process_event, start_values
from .queries import (
    FERMENTATION_BOX,
    FERMENTING,
    GENERATED,
    LOT_SCOPE,
    MANAGE_PERMISSION,
    Facility,
    Lot,
    earliest_start_at,
)


@transaction.atomic
def start_fermentation(actor, data: dict) -> FermentationProcess:
    """Deja el lote en el cajón y en fermentación, en una sola transacción: si algo falla, el lote
    sigue Generado y el cajón como estaba."""
    lot = lock_lot(actor, data["lot_id"])
    if lot.status != GENERATED:
        raise LotInvalidStatus(lot.status)
    check_start_time(lot, data["started_at"])
    responsible = choose_responsible(actor, lot, data["responsible_id"])
    box = find_box(lot, data["facility_id"])
    # Primero se ocupa: un cajón ocupado o inactivo responde eso, no la capacidad.
    box.occupy(lot, kind=FERMENTATION_BOX, actor=actor)
    over_capacity = check_capacity(lot, box, confirmed=data.get("confirm_over_capacity", False))
    process = FermentationProcess.objects.create(
        lot=lot,
        facility=box,
        started_at=data["started_at"],
        over_capacity=over_capacity,
        responsible=responsible,
        created_by=actor,
    )
    lot.advance_status(GENERATED, FERMENTING, actor=actor)
    record_process_event(
        process=process,
        actor=actor,
        action=FermentationProcessAuditEvent.Action.STARTED,
        before={},
        after=start_values(process),
    )
    return process


def lock_lot(actor, lot_id):
    """El lote, con la finca de su parcela bloqueada hasta el final de la transacción."""
    lock_aggregate_root(
        Lot,
        lot_id,
        root="harvest__plot__farm",
        scope=owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"]),
        not_found=LotNotFound,
    )
    return Lot.objects.select_related("harvest__plot__farm").get(pk=lot_id)


def check_start_time(lot, started_at) -> None:
    if started_at > timezone.now():
        raise InvalidFermentation("started_at", "No puede ser una fecha futura.")
    harvest_date = lot.harvest.harvest_date
    if started_at < earliest_start_at(harvest_date):
        raise InvalidFermentation(
            "started_at", f"No puede ser anterior a la cosecha ({harvest_date:%d/%m/%Y})."
        )


def choose_responsible(actor, lot, account_id):
    """La cuenta que responde por la fermentación: debe poder iniciarla y finalizarla en la finca
    del lote. Una cuenta de otro productor no existe para este lote."""
    plot = lot.harvest.plot
    known = (
        get_user_model()
        .objects.filter(pk=account_id, producer_id=plot.farm.producer_id, is_superuser=False)
        .exists()
    )
    if not known:
        raise ResponsibleNotFound()
    account = assignable_person(actor, plot, account_id, MANAGE_PERMISSION)
    if account is None:
        raise ResponsibleNotAvailable()
    return account


def find_box(lot, facility_id):
    """El cajón elegido, si es del productor del lote. Que sea de su finca, del tipo correcto,
    activo y libre lo decide `occupy`."""
    box = (
        Facility.objects.select_related("farm")
        .filter(pk=facility_id, farm__producer_id=lot.harvest.plot.farm.producer_id)
        .first()
    )
    if box is None:
        raise FacilityNotFound()
    return box


def check_capacity(lot, box, *, confirmed: bool) -> bool:
    """Si el lote pesa más de lo que cabe en el cajón. Se pide confirmarlo en vez de rechazarlo: un
    cajón se llena de más en la realidad, y quien registra tiene que poder dejarlo escrito."""
    over = lot.harvest.green_weight_kg > box.capacity_kg
    if over and not confirmed:
        raise LotExceedsCapacity(box.capacity_kg, lot.harvest.green_weight_kg)
    return over
