from django.db import transaction

from apps.common.versioning import check_expected_version

from ..exceptions import StaleHarvestVersion
from ..models import HarvestAuditEvent
from . import queries, rules
from .audit import harvest_values, record_harvest_event


@transaction.atomic
def delete_harvest(actor, harvest_id, expected_version: int) -> None:
    """Elimina una cosecha registrada por error, mientras no forme un lote. El historial se
    conserva, con lo que la cosecha decía."""
    harvest = queries.lock_harvest(actor, harvest_id)
    rules.ensure_not_in_lot(harvest)
    check_expected_version(harvest, expected_version, stale=lambda: StaleHarvestVersion(harvest))
    record_harvest_event(
        harvest=harvest,
        actor=actor,
        action=HarvestAuditEvent.Action.DELETED,
        before=harvest_values(harvest),
        after={},
    )
    harvest.delete()
