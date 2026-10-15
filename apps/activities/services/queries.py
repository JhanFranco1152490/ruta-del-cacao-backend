"""Qué actividades, parcelas y cuentas alcanza quien actúa.

Todo el alcance de esta app pasa por aquí: el productor alcanza lo de todas sus fincas, un
empleado lo de la finca en la que trabaja, y la cuenta técnica lo de cualquiera.
"""

from django.db.models import QuerySet

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter, reaches_all_farms
from apps.common.roles import is_employee

from ..choices import ActivityStatus
from ..exceptions import ActivityNotFound, CompletionNotAllowed, InvalidActivity, PlotNotFound
from ..models import AgriculturalActivity

# Los modelos de la parcela y de la cuenta se toman de las relaciones y no de sus apps: ninguna
# app importa de otra.
Plot = AgriculturalActivity._meta.get_field("plot").related_model
User = AgriculturalActivity._meta.get_field("assignee").related_model

COMPLETE_PERMISSION = "activities.complete_agriculturalactivity"
SCHEDULE_PERMISSION = "activities.add_agriculturalactivity"


def visible_activities(actor) -> QuerySet[AgriculturalActivity]:
    # Los insumos usados se precargan con su insumo: el listado no hace una consulta por fila.
    return (
        AgriculturalActivity.objects.filter(
            **owner_filter(actor, "plot__farm__producer_id", farm="plot__farm_id")
        )
        .select_related("plot__farm", "assignee", "completed_by")
        .prefetch_related("inputs__input")
    )


def list_activities(actor, date_from, date_to, producer_id=None) -> QuerySet[AgriculturalActivity]:
    """Las actividades programadas entre las dos fechas, ambas incluidas. Las realizadas se
    ubican por su fecha programada, como las demás: el calendario muestra lo planeado y si se
    cumplió. `producer_id` solo lo usa la cuenta técnica, que sin él ve las de todos."""
    activities = visible_activities(actor).filter(scheduled_date__range=(date_from, date_to))
    if actor.is_superuser and producer_id is not None:
        activities = activities.filter(plot__farm__producer_id=producer_id)
    return activities.order_by("scheduled_date", "activity_type", "id")


def pending_activities(actor, through, producer_id=None) -> QuerySet[AgriculturalActivity]:
    """Las actividades sin realizar con fecha programada hasta `through`, incluida. No tiene fecha
    mínima: una vencida sigue pendiente mientras no se registre, por viejo que sea su atraso.
    `producer_id` solo lo usa la cuenta técnica, como en `list_activities`."""
    activities = visible_activities(actor).filter(scheduled_date__lte=through)
    activities = activities.exclude(status=ActivityStatus.DONE)
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
    """Las cuentas del productor que `actor` alcanza (su cuenta y sus empleados), activas e
    inactivas, con lo necesario para decidir a quién asignarle una labor. Las inactivas sirven
    para filtrar y para mostrar labores viejas; el formulario solo ofrece las activas.

    Un empleado recibe a la gente que comparte alguna finca con él y al Productor. De cada cuenta,
    las fincas en las que trabaja (`farm_ids`, vacía en el Productor, que vale para todas) y si
    `actor` puede asignarle (`assignable`): con eso el formulario arma la lista de la parcela
    elegida, también sin conexión. No lleva el documento ni los roles: quien asigna no tiene por
    qué verlos. Una cuenta sin nombre se muestra por su correo, como en los historiales: es la
    única forma de reconocerla. La cuenta técnica dice de qué productor; de cualquier otra cuenta
    `producer_id` se ignora.
    """
    if actor.is_superuser:
        if producer_id is None:
            raise InvalidActivity("producer", "Indica de qué productor son los responsables.")
    else:
        producer_id = actor.producer_id
    if producer_id is None:
        return []
    accounts = (
        User.objects.filter(producer_id=producer_id, is_superuser=False)
        .prefetch_related("farms")
        .order_by("last_name", "first_name", "id")
    )
    actor_farms = _farm_ids(actor) if is_employee(actor) else None
    options = []
    for account in accounts:
        employee = is_employee(account)
        farm_ids = sorted(_farm_ids(account), key=str) if employee else []
        if actor_farms is not None and employee and not actor_farms & set(farm_ids):
            continue
        options.append(
            {
                "id": account.pk,
                "full_name": account.get_full_name() or account.email,
                "is_active": account.is_active,
                "farm_ids": farm_ids,
                "assignable": _takes_work(actor, account, employee),
            }
        )
    return options


def assignable_account(actor, plot, account_id):
    """La cuenta, si `actor` puede hacerla responsable de una labor en `plot`: activa, del
    productor de la parcela, con permiso de registrar la realización y, si es un empleado, que
    trabaje en la finca de la parcela. Nunca una cuenta técnica ni de la asociación, que no
    tienen productor."""
    account = User.objects.filter(
        pk=account_id, producer_id=plot.farm.producer_id, is_active=True, is_superuser=False
    ).first()
    if account is None:
        return None
    employee = is_employee(account)
    if employee and plot.farm_id not in _farm_ids(account):
        return None
    return account if _takes_work(actor, account, employee) else None


def _farm_ids(account) -> set:
    # Con `.all()`, para aprovechar las fincas precargadas de una lista.
    return {farm.pk for farm in account.farms.all()}


def _takes_work(actor, account, employee: bool) -> bool:
    """Si a `account` se le puede asignar una labor y `actor` puede hacerlo.

    A quien se le asigna una labor debe poder marcarla como hecha: por eso decide el permiso de
    registrar la realización y no el nombre del rol, que en un rol propio puede ser cualquiera.
    Un empleado sin finca no trabaja en ninguna. Al Productor solo le asigna él mismo (o la cuenta
    técnica): un empleado no le pone labores a quien lo dirige.
    """
    if not account.has_perm(COMPLETE_PERMISSION):
        return False
    if employee:
        return bool(_farm_ids(account))
    return not is_employee(actor)
