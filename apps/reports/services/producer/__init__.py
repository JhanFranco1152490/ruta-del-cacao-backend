"""Los reportes del productor: su unidad productiva, una fila por registro."""

from django.utils import timezone

from apps.common.serializers import full_name

from ...exceptions import ReportTooLarge
from ...report import Report
from ...types import INVENTORY, PRODUCTION, QUALITY, SALES, TITLES, TRACEABILITY
from . import inventory, production, quality, sales, traceability
from .scope import resolve_scope

BUILDERS = {
    PRODUCTION: production.build,
    QUALITY: quality.build,
    INVENTORY: inventory.build,
    SALES: sales.build,
    TRACEABILITY: traceability.build,
}

# Con un año de la unidad productiva más grande no se llega: el límite es para que la cuenta
# técnica sin productor no arme un archivo con todo el sistema.
MAX_ROWS = 5000


def producer_report(actor, query: dict) -> Report:
    scope = resolve_scope(actor, query)
    body = BUILDERS[query["type"]](scope)
    if len(body.rows) > MAX_ROWS:
        raise ReportTooLarge()
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
