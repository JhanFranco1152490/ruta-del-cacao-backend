"""Los lotes en los reportes del productor."""

from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import LotRow, PlotPlace, ScopedLot

from .models import Lot


def lot_in_scope(farm_ids, lot_id) -> ScopedLot | None:
    """El lote, si su cosecha es de una de esas fincas; si no existe o es de otra, `None`."""
    row = (
        Lot.objects.filter(pk=lot_id, harvest__plot__farm_id__in=farm_ids)
        .values("id", "code", "harvest__plot_id", "harvest__plot__farm_id")
        .first()
    )
    if row is None:
        return None
    return ScopedLot(
        lot_id=row["id"],
        farm_id=row["harvest__plot__farm_id"],
        plot_id=row["harvest__plot_id"],
        code=row["code"],
    )


def lot_rows(farm_ids, period: IndicatorPeriod, *, plot_id=None, lot_id=None) -> list[LotRow]:
    """Los lotes de las cosechas del periodo: un lote se ubica en la fecha de su cosecha."""
    lots = Lot.objects.filter(
        harvest__plot__farm_id__in=farm_ids,
        harvest__harvest_date__range=(period.date_from, period.date_to),
    ).select_related("harvest__plot__farm")
    if plot_id is not None:
        lots = lots.filter(harvest__plot_id=plot_id)
    if lot_id is not None:
        lots = lots.filter(pk=lot_id)
    return [
        LotRow(
            lot_id=lot.pk,
            code=lot.code,
            status=lot.get_status_display(),
            harvest_date=lot.harvest.harvest_date,
            place=PlotPlace.of(lot.harvest.plot),
            green_kg=lot.harvest.green_weight_kg,
        )
        for lot in lots
    ]
