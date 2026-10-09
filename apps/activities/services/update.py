from django.db import transaction

from apps.common.versioning import check_expected_version, save_next_version

from ..choices import ActivityType
from ..exceptions import StaleActivityVersion
from ..models import AgriculturalActivity, AgriculturalActivityAuditEvent
from . import queries, rules
from .audit import PLAN_FIELDS, plan_values, record_activity_event

# El nombre del campo del modelo para cada valor de la planeación, para guardar solo lo que cambió.
MODEL_FIELDS = {
    "activity_type": "activity_type",
    "other_description": "other_description",
    "scheduled_date": "scheduled_date",
    "assignee_id": "assignee",
}


@transaction.atomic
def update_activity(actor, activity_id, expected_version: int, data: dict) -> AgriculturalActivity:
    """Edita o reprograma una actividad que todavía no ocurrió. `data` trae solo los campos que
    se quieren cambiar; la parcela no cambia nunca."""
    activity = queries.lock_activity(actor, activity_id)
    # Antes que la versión: una actividad que venció mientras el formulario estaba abierto ya no
    # se reprograma, aunque nadie más la haya tocado.
    rules.ensure_still_planned(activity)
    before = plan_values(activity)
    sent = _sent_values(activity, data)
    if check_expected_version(
        activity,
        expected_version,
        stale=lambda: StaleActivityVersion(activity),
        already_applied=lambda: _differences(before, sent) == {},
    ):
        return activity

    changed = _differences(before, sent)
    if not changed:
        return activity
    after = _validated(activity, before, sent)

    for name, value in after.items():
        if name == "assignee_id":
            activity.assignee = value
        else:
            setattr(activity, name, value)
    save_next_version(activity, [MODEL_FIELDS[name] for name in changed])
    record_activity_event(
        activity=activity,
        actor=actor,
        action=AgriculturalActivityAuditEvent.Action.UPDATED,
        before=before,
        after=plan_values(activity),
    )
    return activity


def _sent_values(activity: AgriculturalActivity, data: dict) -> dict:
    """La planeación como quedaría: lo enviado sobre lo actual. La descripción solo existe con
    "Otro", así que cambiar a otro tipo la quita aunque no se envíe."""
    values = dict(plan_values(activity))
    values.update({name: data[name] for name in PLAN_FIELDS if name in data})
    if "other_description" in data:
        values["other_description"] = (data["other_description"] or "").strip() or None
    elif values["activity_type"] != ActivityType.OTHER:
        values["other_description"] = None
    return values


def _differences(before: dict, sent: dict) -> dict:
    return {name: sent[name] for name in PLAN_FIELDS if str(sent[name]) != str(before[name])}


def _validated(activity: AgriculturalActivity, before: dict, sent: dict) -> dict:
    """Valida solo lo que cambia: una actividad retrasada se reasigna sin moverle la fecha, y una
    cuyo responsable se desactivó se edita sin cambiarlo. Devuelve los valores a guardar."""
    after = {}
    if sent["activity_type"] != before["activity_type"]:
        rules.ensure_type_allowed(sent["activity_type"])
        after["activity_type"] = sent["activity_type"]
    description = rules.clean_description(sent["activity_type"], sent["other_description"])
    if description != before["other_description"]:
        after["other_description"] = description
    if sent["scheduled_date"] != before["scheduled_date"]:
        rules.ensure_not_past(sent["scheduled_date"])
        after["scheduled_date"] = sent["scheduled_date"]
    if str(sent["assignee_id"]) != str(before["assignee_id"]):
        after["assignee_id"] = rules.assignee_for(
            activity.plot.farm.producer_id, sent["assignee_id"]
        )
    return after
