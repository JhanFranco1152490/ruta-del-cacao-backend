"""Datos de prueba de los paneles: cada función deja una cifra en una fuente, con las fábricas de
la app dueña y sin pasar por sus servicios."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.drying.tests.factories import DryingProcessFactory
from apps.harvests.tests.factories import HarvestFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.quality.tests.factories import LotClassificationFactory, LotDiscardFactory
from apps.sales.tests.helpers import sale_with_lines
from apps.warehouse.tests.factories import StockBalanceFactory

PERIOD = {"from": "2026-01-01", "to": "2026-03-31"}
BOGOTA = ZoneInfo("America/Bogota")
# Fuera del periodo: la cosecha de un lote que solo se usa por su calidad, su bodega o su venta.
OUTSIDE = date(2025, 10, 14)


def at(*moment):
    return datetime(*moment, tzinfo=BOGOTA)


def harvest(plot, day, kg):
    return HarvestFactory(plot=plot, harvest_date=day, green_weight_kg=Decimal(kg))


def dry(lot_or_harvest, kg):
    target = (
        {"lot": lot_or_harvest}
        if hasattr(lot_or_harvest, "harvest")
        else {"lot__harvest": lot_or_harvest}
    )
    return DryingProcessFactory(
        **target,
        ended_at=timezone.now(),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal(kg),
        yield_pct=Decimal("35.0"),
        total_sun_hours=Decimal("40.0"),
    )


def _lot(plot, status):
    return LotFactory(harvest__plot=plot, harvest__harvest_date=OUTSIDE, status=status)


def classify(plot, g1, g2, discard, when):
    lot = _lot(plot, LotStatus.CLASSIFIED)
    dry(lot, Decimal(g1) + Decimal(g2) + Decimal(discard))
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal(g1),
        g2_kg=Decimal(g2),
        discard_kg=Decimal(discard),
        discard_reason="mold" if Decimal(discard) else "",
        classified_at=when,
    )
    return lot


def discard_whole(plot, dry_kg, when):
    lot = _lot(plot, LotStatus.DISCARDED)
    dry(lot, dry_kg)
    LotDiscardFactory(lot=lot, discarded_at=when)
    return lot


def stock(plot, grade, kg):
    return StockBalanceFactory(
        lot=_lot(plot, LotStatus.IN_WAREHOUSE), grade=grade, quantity_kg=Decimal(kg)
    )


def sell(plot, day, *lines):
    lot = _lot(plot, LotStatus.IN_WAREHOUSE)
    return sale_with_lines(plot.farm, lot=lot, sale_date=day, lines=lines)
