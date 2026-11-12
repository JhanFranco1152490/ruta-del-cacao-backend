"""Los reportes del productor: su unidad productiva, una fila por registro."""

from django.utils import timezone

from apps.common.serializers import full_name

from ...report import Report
from ...types import INVENTORY, PRODUCTION, QUALITY, TITLES
from . import inventory, production, quality
from .scope import resolve_scope

BUILDERS = {
    PRODUCTION: production.build,
    QUALITY: quality.build,
    INVENTORY: inventory.build,
}


def producer_report(actor, query: dict) -> Report:
    scope = resolve_scope(actor, query)
    body = BUILDERS[query["type"]](scope)
    return Report(
        type=query["type"],
        title=TITLES[query["type"]],
        generated_at=timezone.now(),
        generated_by=full_name(actor),
        filters=scope.filters,
        columns=body.columns,
        rows=body.rows,
        totals=body.totals,
    )
