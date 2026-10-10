"""Qué actividades, parcelas y cuentas alcanza quien actúa.

Todo el alcance de esta app pasa por aquí. Hoy es el productor: el productor y su gente alcanzan lo
suyo, y la cuenta técnica lo de cualquiera. Si algún día un empleado queda limitado a ciertas
fincas, solo cambian estas funciones.
"""

from django.db.models import QuerySet

from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter

from ..exceptions import ActivityNotFound, InvalidActivity, PlotNotFound
from ..models import AgriculturalActivity

# Los modelos de la parcela y de la cuenta se toman de las relaciones y no de sus apps: ninguna
# app importa de otra.
Plot = AgriculturalActivity._meta.get_field("plot").related_model
User = AgriculturalActivity._meta.get_field("assignee").related_model


def visible_activities(actor) -> QuerySet[AgriculturalActivity]:
    # Los insumos usados se precargan con su insumo: el listado no hace una consulta por fila.
    return (
        AgriculturalActivity.objects.filter(**owner_filter(actor, "plot__farm__producer_id"))
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
        scope=owner_filter(actor, "plot__farm__producer_id"),
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
        scope=owner_filter(actor, "farm__producer_id"),
        not_found=PlotNotFound,
    )
    plot.farm = farm
    return plot


def assignee_options(actor, producer_id=None) -> list[dict]:
    """Las cuentas a las que se les puede asignar una labor: las del productor (su cuenta y sus
    empleados), activas e inactivas. Las inactivas sirven para filtrar y para mostrar labores
    viejas; el formulario solo ofrece las activas.

    Solo el id, el nombre y si está activa: es lo mínimo para asignar una labor, y quien la asigna
    no tiene por qué ver el documento ni los roles de sus compañeros. Una cuenta sin nombre se
    muestra por su correo, como en los historiales: es la única forma de reconocerla. La cuenta
    técnica dice de qué productor; de cualquier otra cuenta `producer_id` se ignora.
    """
    if actor.is_superuser:
        if producer_id is None:
            raise InvalidActivity("producer", "Indica de qué productor son los responsables.")
    else:
        producer_id = actor.producer_id
    if producer_id is None:
        return []
    accounts = User.objects.filter(producer_id=producer_id, is_superuser=False).order_by(
        "last_name", "first_name", "id"
    )
    return [
        {
            "id": account.pk,
            "full_name": account.get_full_name() or account.email,
            "is_active": account.is_active,
        }
        for account in accounts
    ]


def assignable_account(producer_id, account_id):
    """La cuenta, si puede ser responsable de una labor de ese productor: activa y suya. Nunca
    una cuenta técnica ni de la asociación, que no tienen productor."""
    return User.objects.filter(
        pk=account_id, producer_id=producer_id, is_active=True, is_superuser=False
    ).first()
