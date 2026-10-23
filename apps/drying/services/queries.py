"""Qué secados, lotes, marquesinas y responsables alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un empleado
lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from datetime import datetime, time

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from apps.common.contracts.assignable import person_options
from apps.common.contracts.postharvest_parameters import drying_parameters
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import DryingNotFound, LotInvalidStatus, LotNotFound
from ..models import DryingLogEntry, DryingProcess

MANAGE_PERMISSION = "drying.manage_drying"

# Los modelos del lote y de la marquesina se toman de la relación y no de su app: ninguna app
# importa de otra.
Lot = DryingProcess._meta.get_field("lot").related_model
Facility = DryingProcess._meta.get_field("facility").related_model

# Los valores de otras apps que esta usa, tal como los guardan sus campos.
FERMENTED = "fermented"
DRYING = "drying"
DRIED = "dried"
SOLAR_DRYER = "solar_dryer"
STATUS_CHANGED = "status_changed"

PROCESS_SCOPE = {
    "field": "lot__harvest__plot__farm__producer_id",
    "farm": "lot__harvest__plot__farm_id",
}
LOT_SCOPE = {"field": "harvest__plot__farm__producer_id", "farm": "harvest__plot__farm_id"}


def with_representation(processes: QuerySet[DryingProcess]) -> QuerySet:
    """Los secados con lo que muestra su representación ya cargado: el lote con su origen, la
    marquesina, el responsable y la bitácora. Así una lista no hace una consulta por fila."""
    return processes.select_related(
        "lot__harvest__plot__farm__producer",
        "lot__harvest__variety",
        "lot__harvest__collector",
        "lot__harvest__registered_by",
        "facility",
        "responsible",
    ).prefetch_related(
        Prefetch(
            "logs",
            queryset=DryingLogEntry.objects.select_related("recorded_by").order_by("measured_at"),
        )
    )


def visible_dryings(actor) -> QuerySet[DryingProcess]:
    return with_representation(
        DryingProcess.objects.filter(
            **owner_filter(actor, PROCESS_SCOPE["field"], farm=PROCESS_SCOPE["farm"])
        )
    )


def list_dryings(actor, *, farm=None, producer=None) -> QuerySet[DryingProcess]:
    """Los secados en curso, del más antiguo al más reciente. `producer` solo lo usa la cuenta
    técnica, que sin él ve los de todos."""
    processes = visible_dryings(actor).filter(lot__status=DRYING)
    if farm is not None:
        processes = processes.filter(lot__harvest__plot__farm_id=farm)
    if producer is not None and actor.is_superuser:
        processes = processes.filter(lot__harvest__plot__farm__producer_id=producer)
    return processes.order_by("started_at", "lot__code")


def get_drying(actor, lot_id) -> DryingProcess:
    process = visible_dryings(actor).filter(pk=lot_id).first()
    if process is None:
        raise DryingNotFound()
    return process


def lock_process(actor, lot_id) -> DryingProcess:
    """El secado, con la finca de su lote bloqueada hasta el final de la transacción."""
    lock_aggregate_root(
        DryingProcess,
        lot_id,
        root="lot__harvest__plot__farm",
        scope=owner_filter(actor, PROCESS_SCOPE["field"], farm=PROCESS_SCOPE["farm"]),
        not_found=DryingNotFound,
    )
    return DryingProcess.objects.select_related(
        "lot__harvest__plot__farm", "facility__farm", "responsible"
    ).get(pk=lot_id)


def start_options(actor, lot_id) -> dict:
    """Lo que necesita el formulario para iniciar el secado de un lote Fermentado o corregir el
    inicio de uno sin bitácora: las marquesinas libres de la finca del lote (más la que ya ocupa,
    al corregir), quién puede ser responsable ahí, el rango esperado de la humedad de entrada y
    desde cuándo puede empezar."""
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
    parameters = drying_parameters(farm.producer_id)
    return {
        "facilities": _free_dryers(farm, lot),
        "responsibles": responsible_options(actor, farm),
        "entry_moisture_range": {
            "min": parameters.entry_moisture_min_pct,
            "max": parameters.entry_moisture_max_pct,
        },
        "earliest_start_at": earliest_start_at(lot),
    }


def earliest_start_at(lot) -> datetime:
    """El momento en que el lote quedó Fermentado, que registra su historial. Un lote sin ese
    evento (cargado antes de que existiera la fermentación) puede empezar desde el día de su
    cosecha."""
    fermented = (
        lot.audit_events.filter(action=STATUS_CHANGED, changes__status__after=FERMENTED)
        .order_by("-occurred_at")
        .values_list("occurred_at", flat=True)
        .first()
    )
    if fermented is not None:
        return fermented
    return timezone.make_aware(datetime.combine(lot.harvest.harvest_date, time.min))


def responsible_options(actor, farm) -> list[dict]:
    """Las cuentas que `actor` puede nombrar responsables de un secado en `farm`: activas, con el
    permiso de iniciarlo y finalizarlo, y que trabajen en esa finca o en todas."""
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
    if lot.status == FERMENTED:
        return True
    process = DryingProcess.objects.filter(pk=lot.pk).first()
    return lot.status == DRYING and process is not None and not process.logs.exists()


def _free_dryers(farm, lot) -> list:
    return list(
        Facility.objects.filter(farm=farm, facility_type=SOLAR_DRYER, is_active=True)
        .filter(Q(current_lot__isnull=True) | Q(current_lot=lot))
        .order_by("name_normalized", "id")
    )
