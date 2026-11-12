"""Los lotes cerrados de calidad en los reportes del productor: los mismos de la pestaña de
cerrados, con su fecha de cierre en la hora de Bogotá."""

from django.utils.timezone import localdate

from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.contracts.reports import PlotPlace, QualityRow
from apps.common.figures import ZERO

from .choices import DiscardReason
from .services.queries import CLASSIFIED_STATUSES, Lot, closed_in_period

CLASSIFIED = "Clasificado"
DISCARDED = "Descartado"


def quality_rows(farm_ids, period: IndicatorPeriod, *, plot_id=None, lot_id=None):
    lots = Lot.objects.filter(harvest__plot__farm_id__in=farm_ids)
    if plot_id is not None:
        lots = lots.filter(harvest__plot_id=plot_id)
    if lot_id is not None:
        lots = lots.filter(pk=lot_id)
    lots = closed_in_period(lots, {"closed_from": period.date_from, "closed_to": period.date_to})
    return _rows(lots)


def quality_by_lot(lot_ids) -> list[QualityRow]:
    """El cierre de cada uno de esos lotes que ya cerró, sin importar cuándo."""
    if not lot_ids:
        return []
    return _rows(closed_in_period(Lot.objects.filter(pk__in=lot_ids), {}))


def _rows(lots) -> list[QualityRow]:
    lots = lots.select_related("harvest__plot__farm", "drying", "classification", "discard")
    return [_row(lot) for lot in lots]


def _row(lot) -> QualityRow:
    dry_kg = lot.drying.dry_weight_kg
    if lot.status in CLASSIFIED_STATUSES:
        closing = lot.classification
        result, closed_at = CLASSIFIED, closing.classified_at
        kg = (closing.g1_kg, closing.g2_kg, closing.discard_kg)
        reason, detail = closing.discard_reason, closing.discard_detail
    else:
        closing = lot.discard
        result, closed_at = DISCARDED, closing.discarded_at
        kg = (ZERO, ZERO, dry_kg)
        reason, detail = closing.reason, closing.detail
    g1_kg, g2_kg, discard_kg = kg
    return QualityRow(
        lot_id=lot.pk,
        lot_code=lot.code,
        place=PlotPlace.of(lot.harvest.plot),
        closed_on=localdate(closed_at),
        result=result,
        whole_discard=result == DISCARDED,
        dry_kg=dry_kg,
        g1_kg=g1_kg,
        g2_kg=g2_kg,
        discard_kg=discard_kg,
        discard_reason=DiscardReason(reason).label if reason else "",
        discard_detail=detail,
    )
