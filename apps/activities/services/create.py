from django.db import transaction

from apps.common.db import save_translating_unique
from apps.common.ownership import owns

from ..exceptions import ActivityIdConflict
from ..models import AgriculturalActivity, AgriculturalActivityAuditEvent
from . import queries, rules
from .audit import plan_values, record_activity_event

ID_CONSTRAINT = "activities_agriculturalactivity_pkey"


@transaction.atomic
def create_activity(actor, data: dict) -> tuple[AgriculturalActivity, bool]:
    """Programa una actividad en una parcela del productor de la sesión. Devuelve `(actividad,
    creada)`.

    El cliente envía el `id` que generó: reenviar el mismo `id` con el mismo contenido devuelve la
    actividad ya creada (`creada=False`), de modo que reintentar un envío cortado nunca duplica.
    """
    activity_id = data.get("id")
    if activity_id is not None and (existing := _existing(activity_id)) is not None:
        return _resent(existing, actor, data), False

    plot = queries.lock_plot(actor, data["plot_id"])
    # Con la finca bloqueada, un envío del mismo registro que llegó a la vez ya terminó: si la
    # creó, se responde como un reenvío.
    if activity_id is not None and (existing := _existing(activity_id)) is not None:
        return _resent(existing, actor, data), False
    rules.ensure_plot_open(plot)
    rules.ensure_type_allowed(data["activity_type"])
    description = rules.clean_description(data["activity_type"], data.get("other_description"))
    rules.ensure_not_past(data["scheduled_date"])
    assignee = rules.assignee_for(plot.farm.producer_id, data["assignee_id"])

    activity = AgriculturalActivity(
        plot=plot,
        activity_type=data["activity_type"],
        other_description=description,
        scheduled_date=data["scheduled_date"],
        assignee=assignee,
    )
    if activity_id is not None:
        activity.pk = activity_id
    # El mismo `id` en una parcela de otra finca no pasa por el mismo bloqueo: el choque llega
    # como clave primaria repetida.
    existing = save_translating_unique(
        lambda: activity.save(force_insert=True),
        constraint=ID_CONSTRAINT,
        duplicate=ActivityIdConflict,
        find_existing=lambda: _existing(activity.pk) if activity_id is not None else None,
    )
    if existing is not None:
        return _resent(existing, actor, data), False
    record_activity_event(
        activity=activity,
        actor=actor,
        action=AgriculturalActivityAuditEvent.Action.CREATED,
        before={},
        after=plan_values(activity),
    )
    return activity, True


def _existing(activity_id) -> AgriculturalActivity | None:
    return AgriculturalActivity.objects.select_related("plot__farm").filter(pk=activity_id).first()


def _resent(existing: AgriculturalActivity, actor, data: dict) -> AgriculturalActivity:
    if not owns(actor, existing.plot.farm.producer_id):
        raise ActivityIdConflict()
    sent = {
        "plot_id": str(data["plot_id"]),
        "activity_type": data["activity_type"],
        "other_description": (data.get("other_description") or "").strip() or None,
        "scheduled_date": data["scheduled_date"],
        "assignee_id": str(data["assignee_id"]),
    }
    stored = {
        "plot_id": str(existing.plot_id),
        "activity_type": existing.activity_type,
        "other_description": existing.other_description,
        "scheduled_date": existing.scheduled_date,
        "assignee_id": str(existing.assignee_id),
    }
    if sent != stored:
        raise ActivityIdConflict()
    return existing
