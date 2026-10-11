from django.db import transaction

from apps.common.versioning import check_expected_version

from ..exceptions import StaleActivityVersion
from ..models import AgriculturalActivity, AgriculturalActivityAuditEvent
from . import queries, rules
from .audit import plan_values, record_activity_event


@transaction.atomic
def delete_activity(actor, activity_id, expected_version: int) -> None:
    """Elimina una actividad programada por error. Solo lo que todavía no ocurrió: una realizada o
    una vencida son evidencia de lo que pasó y se quedan."""
    activity = queries.lock_activity(actor, activity_id)
    rules.ensure_still_planned(activity)
    check_expected_version(
        activity, expected_version, stale=lambda: StaleActivityVersion(activity)
    )
    remove_activity(activity, actor)


def remove_activity(activity: AgriculturalActivity, actor) -> None:
    """Elimina la actividad y deja el rastro, con lo que tenía planeado. Quien llama ya decidió que
    se puede borrar."""
    record_activity_event(
        activity=activity,
        actor=actor,
        action=AgriculturalActivityAuditEvent.Action.DELETED,
        before=plan_values(activity),
        after={},
    )
    activity.delete()
