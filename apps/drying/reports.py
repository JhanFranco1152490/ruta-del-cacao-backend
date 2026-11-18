"""Lo que dio el secado de cada lote, para los reportes de producción y de trazabilidad."""

from django.utils.timezone import localdate

from apps.common.contracts.reports import DryingResult

from .models import DryingProcess


def drying_results(lot_ids) -> list[DryingResult]:
    """Solo los secados terminados: uno en curso todavía no tiene peso seco."""
    if not lot_ids:
        return []
    rows = DryingProcess.objects.filter(lot_id__in=lot_ids, ended_at__isnull=False).values(
        "lot_id", "ended_at", "dry_weight_kg", "yield_pct"
    )
    return [
        DryingResult(
            lot_id=row["lot_id"],
            ended_on=localdate(row["ended_at"]),
            dry_kg=row["dry_weight_kg"],
            yield_pct=row["yield_pct"],
        )
        for row in rows
    ]
