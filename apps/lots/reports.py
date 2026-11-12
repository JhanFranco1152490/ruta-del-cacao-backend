"""Los lotes en los reportes del productor."""

from apps.common.contracts.reports import ScopedLot

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
