"""La fecha de conformado de los lotes de demostración.

El servicio que conforma un lote le pone la hora en que se guarda, y no acepta una del pasado; la
fermentación, el secado y lo que sigue sí aceptan horas del pasado. Por eso la semilla deja lotes
conformados hoy con una fermentación de hace semanas, y su historia mostraría el conformado después
de la venta. Este paso corre su conformado a la tarde del día de la cosecha.
"""

from datetime import datetime, time, timedelta

from django.db.models import F
from django.utils import timezone

from apps.lots.models import Lot

from .catalog import PRODUCERS

# A qué hora del día de la cosecha queda conformado: una tarde, como en el campo.
FORMED_AT = time(17, 0)
# Si la fermentación empezó antes de esa hora, el lote queda conformado una hora antes de ella.
BEFORE_FERMENTATION = timedelta(hours=1)


def _formed_at(lot) -> datetime:
    afternoon = timezone.make_aware(datetime.combine(lot.harvest.harvest_date, FORMED_AT))
    return min(afternoon, lot.fermentation.started_at - BEFORE_FERMENTATION)


def align_lot_dates() -> list[str]:
    """Corre el conformado de cada lote de demostración que quedó después del inicio de su
    fermentación. No toca uno conformado desde la aplicación, que siempre queda antes."""
    documents = [definition["identity_document"] for definition in PRODUCERS]
    lots = Lot.objects.filter(
        harvest__plot__farm__producer__identity_document__in=documents,
        fermentation__started_at__lt=F("created_at"),
    ).select_related("harvest", "fermentation")
    moved = 0
    for lot in lots:
        Lot.objects.filter(pk=lot.pk).update(created_at=_formed_at(lot))
        moved += 1
    return [f"Conformado de {moved} lotes corrido al día de su cosecha"] if moved else []
