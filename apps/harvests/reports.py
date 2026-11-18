"""Las cosechas en los reportes del productor."""

from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import HarvestRow, PlotPlace
from apps.common.serializers import full_name

from .models import Harvest


def harvest_rows(farm_ids, period: IndicatorPeriod, *, plot_id=None, lot_id=None):
    harvests = Harvest.objects.filter(
        plot__farm_id__in=farm_ids,
        harvest_date__range=(period.date_from, period.date_to),
    ).select_related("plot__farm", "variety", "collector", "lot")
    if plot_id is not None:
        harvests = harvests.filter(plot_id=plot_id)
    if lot_id is not None:
        harvests = harvests.filter(lot__pk=lot_id)
    return [_row(harvest) for harvest in harvests]


def _row(harvest) -> HarvestRow:
    lot = getattr(harvest, "lot", None)
    return HarvestRow(
        harvest_id=harvest.pk,
        harvest_date=harvest.harvest_date,
        place=PlotPlace.of(harvest.plot),
        variety=harvest.variety.name,
        collector=full_name(harvest.collector),
        green_kg=harvest.green_weight_kg,
        lot_id=lot.pk if lot else None,
        lot_code=lot.code if lot else None,
        lot_status=lot.get_status_display() if lot else None,
    )
