"""Qué fermentaciones, lotes, cajones y responsables alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un empleado
lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from datetime import datetime, time

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from apps.common.contracts.assignable import person_options
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import FermentationNotFound, LotInvalidStatus, LotNotFound
from ..models import FermentationProcess, FermentationTurn

MANAGE_PERMISSION = "fermentation.manage_fermentation"

# Los modelos del lote y del cajón se toman de la relación y no de su app: ninguna app importa de
# otra.
Lot = FermentationProcess._meta.get_field("lot").related_model
Facility = FermentationProcess._meta.get_field("facility").related_model

# Los valores de otras apps que esta usa, tal como los guardan sus campos.
GENERATED = "generated"
FERMENTING = "fermenting"
FERMENTED = "fermented"
FERMENTATION_BOX = "fermentation_box"

PROCESS_SCOPE = {
    "field": "lot__harvest__plot__farm__producer_id",
    "farm": "lot__harvest__plot__farm_id",
}
LOT_SCOPE = {"field": "harvest__plot__farm__producer_id", "farm": "harvest__plot__farm_id"}


def with_representation(processes: QuerySet[FermentationProcess]) -> QuerySet:
    """Las fermentaciones con lo que muestra su representación ya cargado: el lote con su origen,
    el cajón, el responsable y los volteos. Así una lista no hace una consulta por fila."""
    return processes.select_related(
        "lot__harvest__plot__farm__producer",
        "lot__harvest__variety",
        "lot__harvest__collector",
        "lot__harvest__registered_by",
        "facility",
        "responsible",
    ).prefetch_related(
        Prefetch(
            "turns",
            queryset=FermentationTurn.objects.select_related("recorded_by").order_by("turned_at"),
        )
    )


def visible_fermentations(actor) -> QuerySet[FermentationProcess]:
    return with_representation(
        FermentationProcess.objects.filter(
            **owner_filter(actor, PROCESS_SCOPE["field"], farm=PROCESS_SCOPE["farm"])
        )
    )


def list_fermentations(actor, *, farm=None, producer=None) -> QuerySet[FermentationProcess]:
    """Las fermentaciones en curso, de la más antigua a la más reciente. `producer` solo lo usa la
    cuenta técnica, que sin él ve las de todos."""
    processes = visible_fermentations(actor).filter(lot__status=FERMENTING)
    if farm is not None:
        processes = processes.filter(lot__harvest__plot__farm_id=farm)
    if producer is not None and actor.is_superuser:
        processes = processes.filter(lot__harvest__plot__farm__producer_id=producer)
    return processes.order_by("started_at", "lot__code")


def get_fermentation(actor, lot_id) -> FermentationProcess:
    process = visible_fermentations(actor).filter(pk=lot_id).first()
    if process is None:
        raise FermentationNotFound()
    return process


def lock_process(actor, lot_id) -> FermentationProcess:
    """La fermentación, con la finca de su lote bloqueada hasta el final de la transacción."""
    lock_aggregate_root(
        FermentationProcess,
        lot_id,
        root="lot__harvest__plot__farm",
        scope=owner_filter(actor, PROCESS_SCOPE["field"], farm=PROCESS_SCOPE["farm"]),
        not_found=FermentationNotFound,
    )
    return FermentationProcess.objects.select_related(
        "lot__harvest__plot__farm", "facility__farm", "responsible"
    ).get(pk=lot_id)


def start_options(actor, lot_id) -> dict:
    """Lo que necesita el formulario para iniciar la fermentación de un lote Generado o corregir el
    inicio de una sin volteos: los cajones libres de la finca del lote (más el que ya ocupa, al
    corregir), quién puede ser responsable ahí, el peso del lote y desde cuándo puede empezar."""
    lot = (
        Lot.objects.filter(**owner_filter(actor, LOT_SCOPE["field"], farm=LOT_SCOPE["farm"]))
        .select_related("harvest__plot__farm")
        .filter(pk=lot_id)
        .first()
    )
    if lot is None:
        raise LotNotFound()
    if not _can_start_or_correct(lot):
        raise LotInvalidStatus(lot.status)
    farm = lot.harvest.plot.farm
    return {
        "facilities": _free_boxes(farm, lot),
        "responsibles": responsible_options(actor, farm),
        "green_weight_kg": lot.harvest.green_weight_kg,
        "earliest_start_at": earliest_start_at(lot.harvest.harvest_date),
    }


def earliest_start_at(harvest_date) -> datetime:
    """El comienzo del día de la cosecha: no se fermenta cacao que no se ha recolectado. No se usa
    la hora en que se conformó el lote, porque se puede registrar tarde."""
    return timezone.make_aware(datetime.combine(harvest_date, time.min))


def responsible_options(actor, farm) -> list[dict]:
    """Las cuentas que `actor` puede nombrar responsables de una fermentación en `farm`: activas,
    con el permiso de iniciarla y finalizarla, y que trabajen en esa finca o en todas."""
    options = person_options(
        actor,
        farm.producer_id,
        MANAGE_PERMISSION,
        # El productor sale de la finca del lote, así que nunca falta.
        producer_required=LotNotFound,
    )
    return [
        option
        for option in options
        if option["is_active"]
        and option["assignable"]
        and (option["all_farms"] or farm.pk in option["farm_ids"])
    ]


def _can_start_or_correct(lot) -> bool:
    if lot.status == GENERATED:
        return True
    process = FermentationProcess.objects.filter(pk=lot.pk).first()
    return lot.status == FERMENTING and process is not None and not process.turns.exists()


def _free_boxes(farm, lot) -> list:
    return list(
        Facility.objects.filter(farm=farm, facility_type=FERMENTATION_BOX, is_active=True)
        .filter(Q(current_lot__isnull=True) | Q(current_lot=lot))
        .order_by("name_normalized", "id")
    )
