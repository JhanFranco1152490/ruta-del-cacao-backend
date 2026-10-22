"""Qué actividades, parcelas y cuentas alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un
empleado lo de la finca en la que trabaja, y la cuenta técnica lo de cualquiera.
"""

from django.db.models import QuerySet

from apps.common.contracts.activity_details import activity_detail_prefetch
from apps.common.contracts.assignable import assignable_person, person_options
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter, reaches_all_farms

from ..choices import ActivityStatus
from ..exceptions import ActivityNotFound, CompletionNotAllowed, InvalidActivity, PlotNotFound
from ..models import AgriculturalActivity

# El modelo de la parcela se toma de la relación y no de su app: ninguna app importa de otra.
Plot = AgriculturalActivity._meta.get_field("plot").related_model

COMPLETE_PERMISSION = "activities.complete_agriculturalactivity"
SCHEDULE_PERMISSION = "activities.add_agriculturalactivity"


def with_representation(activities: QuerySet[AgriculturalActivity]) -> QuerySet:
    """Las actividades con lo que necesita su representación ya precargado: los insumos usados
    con su insumo, y lo que otras apps agregan (el resultado de un monitoreo) con lo que ellas
    piden. Así un listado no hace una consulta por fila."""
    return activities.select_related("plot__farm", "assignee", "completed_by").prefetch_related(
        "inputs__input", *activity_detail_prefetch()
    )


def visible_activities(actor) -> QuerySet[AgriculturalActivity]:
    return with_representation(
        AgriculturalActivity.objects.filter(
            **owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id")
        )
    )


def list_activities(actor, date_from, date_to, producer_id=None) -> QuerySet[AgriculturalActivity]:
    """Las actividades programadas entre las dos fechas, ambas incluidas. Las realizadas se
    ubican por su fecha programada, como las demás: el calendario muestra lo planeado y si se
    cumplió. `producer_id` solo lo usa la cuenta técnica, que sin él ve las de todos."""
    activities = visible_activities(actor).filter(scheduled_date__range=(date_from, date_to))
    if actor.is_superuser and producer_id is not None:
        activities = activities.filter(plot__farm__producer_id=producer_id)
    return activities.order_by("scheduled_date", "activity_type", "id")


def pending_activities(
    actor, through, producer_id=None, activity_type=None
) -> QuerySet[AgriculturalActivity]:
    """Las actividades sin realizar con fecha programada hasta `through`, incluida. No tiene fecha
    mínima: una vencida sigue pendiente mientras no se registre, por viejo que sea su atraso.
    `producer_id` solo lo usa la cuenta técnica, como en `list_activities`. `activity_type` deja
    solo las de un tipo: Sanidad pide así los monitoreos por registrar."""
    activities = visible_activities(actor).filter(scheduled_date__lte=through)
    activities = activities.exclude(status=ActivityStatus.DONE)
    if activity_type is not None:
        activities = activities.filter(activity_type=activity_type)
    if actor.is_superuser and producer_id is not None:
        activities = activities.filter(plot__farm__producer_id=producer_id)
    return activities.order_by("scheduled_date", "activity_type", "id")


def get_activity(actor, activity_id) -> AgriculturalActivity:
    activity = visible_activities(actor).filter(pk=activity_id).first()
    if activity is None:
        raise ActivityNotFound()
    return activity


def lock_activity(actor, activity_id) -> AgriculturalActivity:
    """La actividad, con la finca de su parcela bloqueada hasta el final de la transacción."""
    activity, farm = lock_aggregate_root(
        AgriculturalActivity,
        activity_id,
        root="plot__farm",
        scope=owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id"),
        not_found=ActivityNotFound,
    )
    activity.plot.farm = farm
    return activity


def lock_plot(actor, plot_id):
    """La parcela donde se va a programar, con su finca bloqueada hasta el final de la
    transacción."""
    plot, farm = lock_aggregate_root(
        Plot,
        plot_id,
        root="farm",
        scope=owner_filter(actor, "farm__producer_id", farm="farm_id"),
        not_found=PlotNotFound,
    )
    plot.farm = farm
    return plot


def ensure_can_complete(actor, activity) -> None:
    """Registra la realización el responsable, quien programa labores en la finca (el
    Capataz/Operario o un rol propio con ese permiso) o el Productor y la cuenta técnica. Quien
    solo registra lo suyo no cierra las labores de un compañero. El alcance de la finca y el
    permiso de registrar ya los revisaron la vista y `lock_activity`."""
    if (
        activity.assignee_id == actor.pk
        or reaches_all_farms(actor)
        or actor.has_perm(SCHEDULE_PERMISSION)
    ):
        return
    raise CompletionNotAllowed()


def assignee_options(actor, producer_id=None) -> list[dict]:
    """Las cuentas a las que `actor` puede asignar una labor; ver `person_options`."""
    return person_options(
        actor,
        producer_id,
        COMPLETE_PERMISSION,
        producer_required=lambda: InvalidActivity(
            "producer", "Indica de qué productor son los responsables."
        ),
    )


def assignable_account(actor, plot, account_id):
    """La cuenta, si `actor` puede hacerla responsable de una labor en `plot`: activa, del
    productor de la parcela, con permiso de registrar la realización y, si es un empleado, que
    trabaje en la finca de la parcela."""
    return assignable_person(actor, plot, account_id, COMPLETE_PERMISSION)
