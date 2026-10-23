"""Qué secados alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un empleado
lo de las fincas en las que trabaja, y la cuenta técnica lo de cualquiera.
"""

from django.db.models import Prefetch, QuerySet

from apps.common.ownership import owner_filter

from ..exceptions import DryingNotFound
from ..models import DryingLogEntry, DryingProcess

# El valor del estado del lote que esta app usa, tal como lo guarda su campo.
DRYING = "drying"

PROCESS_SCOPE = {
    "field": "lot__harvest__plot__farm__producer_id",
    "farm": "lot__harvest__plot__farm_id",
}


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
