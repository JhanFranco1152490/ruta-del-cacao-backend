"""Iniciar el secado de un lote en una marquesina, y las reglas del inicio que comparte con
corregirlo."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.common.contracts.assignable import assignable_person
from apps.common.contracts.postharvest_parameters import drying_parameters
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import (
    EntryMoistureOutOfRange,
    FacilityNotFound,
    InvalidDrying,
    LotInvalidStatus,
    LotNotFound,
    ResponsibleNotAvailable,
    ResponsibleNotFound,
)
from ..models import DryingProcess, DryingProcessAuditEvent
from .audit import record_process_event, start_values
from .queries import (
    DRYING,
    FERMENTED,
    LOT_SCOPE,
    MANAGE_PERMISSION,
    SOLAR_DRYER,
    Facility,
    Lot,
    earliest_start_at,
)


@transaction.atomic
def start_drying(actor, data: dict) -> DryingProcess:
    """Deja el lote en la marquesina y en secado, en una sola transacción: si algo falla, el lote
    sigue Fermentado y la marquesina como estaba."""
    lot = lock_lot(actor, data["lot_id"])
    if lot.status != FERMENTED:
        raise LotInvalidStatus(lot.status)
    check_start_time(lot, data["started_at"])
    responsible = choose_responsible(actor, lot, data["responsible_id"])
    dryer = find_dryer(lot, data["facility_id"])
    # Primero se ocupa: una marquesina ocupada o inactiva responde eso, no la humedad.
    dryer.occupy(lot, kind=SOLAR_DRYER, actor=actor)
    out_of_range = check_entry_moisture(
        lot,
        data["entry_moisture_pct"],
        confirmed=data.get("confirm_entry_moisture", False),
    )
    process = DryingProcess.objects.create(
        lot=lot,
        facility=dryer,
        started_at=data["started_at"],
        entry_moisture_pct=data["entry_moisture_pct"],
        entry_moisture_out_of_range=out_of_range,
        responsible=responsible,
        created_by=actor,
    )
    lot.advance_status(FERMENTED, DRYING, actor=actor)
    record_process_event(
        process=process,
        actor=actor,
        action=DryingProcessAuditEvent.Action.STARTED,
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
        raise InvalidDrying("started_at", "No puede ser una fecha futura.")
    earliest = earliest_start_at(lot)
    if started_at < earliest:
        raise InvalidDrying(
            "started_at",
            "No puede ser anterior al fin de la fermentación "
            f"({timezone.localtime(earliest):%d/%m/%Y %H:%M}).",
        )


def check_entry_moisture(lot, moisture, *, confirmed: bool) -> bool:
    """Si la humedad de entrada sale del rango que el productor espera. Se pide confirmarla en vez
    de rechazarla: el grano llega como llega, y quien registra tiene que poder dejarlo escrito."""
    parameters = drying_parameters(lot.harvest.plot.farm.producer_id)
    minimum = parameters.entry_moisture_min_pct
    maximum = parameters.entry_moisture_max_pct
    out_of_range = not minimum <= moisture <= maximum
    if out_of_range and not confirmed:
        raise EntryMoistureOutOfRange(minimum, maximum)
    return out_of_range


def choose_responsible(actor, lot, account_id):
    """La cuenta que responde por el secado: debe poder iniciarlo y finalizarlo en la finca del
    lote. Una cuenta de otro productor no existe para este lote."""
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


def find_dryer(lot, facility_id):
    """La marquesina elegida, si es del productor del lote. Que sea de su finca, del tipo correcto,
    activa y libre lo decide `occupy`."""
    dryer = (
        Facility.objects.select_related("farm")
        .filter(pk=facility_id, farm__producer_id=lot.harvest.plot.farm.producer_id)
        .first()
    )
    if dryer is None:
        raise FacilityNotFound()
    return dryer
