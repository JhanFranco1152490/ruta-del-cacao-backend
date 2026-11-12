"""Las fechas de la fermentación de cada lote, para el reporte de trazabilidad."""

from django.utils.timezone import localdate

from apps.common.contracts.reports import FermentationDates

from .models import FermentationProcess


def fermentation_dates(lot_ids) -> list[FermentationDates]:
    if not lot_ids:
        return []
    rows = FermentationProcess.objects.filter(lot_id__in=lot_ids).values(
        "lot_id", "started_at", "ended_at"
    )
    return [
        FermentationDates(
            lot_id=row["lot_id"],
            started_on=localdate(row["started_at"]),
            ended_on=localdate(row["ended_at"]) if row["ended_at"] else None,
        )
        for row in rows
    ]
