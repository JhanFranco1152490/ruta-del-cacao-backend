from apps.common.audit import field_changes

from ..models import AgriculturalActivity, AgriculturalActivityAuditEvent

# Lo que describe la planeación de una actividad, con los valores que entrega la API.
PLAN_FIELDS = ("activity_type", "other_description", "scheduled_date", "assignee_id")


def plan_values(activity: AgriculturalActivity) -> dict:
    return {field: getattr(activity, field) for field in PLAN_FIELDS}


def record_activity_event(
    *, activity: AgriculturalActivity, actor, action: str, before: dict, after: dict
) -> AgriculturalActivityAuditEvent:
    changes = field_changes(before, after)
    return AgriculturalActivityAuditEvent.record(
        activity=activity,
        activity_ref=activity.pk,
        plot_ref=activity.plot_id,
        actor=actor,
        action=action,
        changed_fields=changes.keys(),
        version=activity.version,
        changes=changes,
    )
