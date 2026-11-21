"""Un lote que pasó por todo el proceso, para las pruebas que recorren su historia: la interna y
la pública."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.buyers.tests.factories import BuyerFactory
from apps.drying.tests.factories import DryingLogEntryFactory, DryingProcessFactory
from apps.farms.tests.factories import FarmFactory
from apps.fermentation.tests.factories import (
    FermentationProcessFactory,
    FermentationTurnFactory,
)
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory
from apps.quality.tests.factories import (
    LotClassificationFactory,
    QualityEvaluationFactory,
)
from apps.sales.tests.helpers import sale_with_lines
from apps.warehouse.tests.factories import (
    StockBalanceFactory,
    StockEntryFactory,
    StockExitFactory,
    WarehouseFactory,
)


class Journey:
    """Un lote de La Esperanza que pasó por todo el proceso hace unas semanas, y cuentas para
    consultarlo desde dentro y fuera de su alcance."""

    def __init__(self):
        self.producer = ProducerFactory(member_code="PROD-000123")
        self.farm = FarmFactory(producer=self.producer, number=2, name="La Esperanza")
        self.other_farm = FarmFactory(producer=self.producer, number=3)
        self.plot = characterized_plot(farm=self.farm, number=5, name="Lote del río")
        self.owner = make_producer_owner(self.producer)
        self.start = timezone.now() - timedelta(days=40)

    def day(self, days, hours=0):
        return self.start + timedelta(days=days, hours=hours)

    def lot(self, status, **fields):
        lot = LotFactory(
            harvest__plot=self.plot,
            harvest__harvest_date=timezone.localdate(self.start),
            harvest__green_weight_kg=Decimal("120.0"),
            status=status,
            **fields,
        )
        # El conformado es de la misma tarde de la cosecha, no de hoy.
        Lot.objects.filter(pk=lot.pk).update(created_at=self.day(0, 6))
        lot.refresh_from_db()
        return lot

    def fermented(self, lot):
        process = FermentationProcessFactory(
            lot=lot, started_at=self.day(1), ended_at=self.day(7), facility__farm=self.farm
        )
        for hours in (24, 48):
            FermentationTurnFactory(process=process, turned_at=self.day(1, hours))

    def dried(self, lot, dry_weight="45.0"):
        process = DryingProcessFactory(
            lot=lot,
            started_at=self.day(7, 1),
            ended_at=self.day(15),
            final_moisture_pct=Decimal("7.0"),
            dry_weight_kg=Decimal(dry_weight),
            yield_pct=Decimal("37.5"),
            total_sun_hours=Decimal("46.0"),
            facility__farm=self.farm,
        )
        DryingLogEntryFactory(process=process, day=1)

    def evaluated(self, lot):
        QualityEvaluationFactory(lot=lot, evaluated_at=self.day(16))

    def sold_lot(self):
        lot = self.lot(LotStatus.IN_WAREHOUSE)
        self.fermented(lot)
        self.dried(lot)
        self.evaluated(lot)
        LotClassificationFactory(
            lot=lot,
            g1_kg=Decimal("32.5"),
            g2_kg=Decimal("8.0"),
            discard_kg=Decimal("4.5"),
            discard_reason="mold",
            classified_at=self.day(17),
        )
        warehouse = WarehouseFactory(farm=self.farm, name="Bodega principal")
        StockEntryFactory(
            lot=lot,
            warehouse=warehouse,
            entry_date=timezone.localdate(self.day(18)),
            g1_kg=Decimal("32.5"),
            g2_kg=Decimal("8.0"),
        )
        StockBalanceFactory(lot=lot, grade="g1", quantity_kg=Decimal("12.0"), warehouse=warehouse)
        StockBalanceFactory(lot=lot, grade="g2", quantity_kg=Decimal("8.0"), warehouse=warehouse)
        StockExitFactory(
            lot=lot,
            quantity_kg=Decimal("0.5"),
            exit_date=timezone.localdate(self.day(20)),
            reason="sample",
        )
        buyer = BuyerFactory(producer=self.producer, name="Chocolates del Oriente S.A.S.")
        sale_with_lines(
            self.farm,
            lines=(("g1", "20.0", 18500),),
            lot=lot,
            buyer=buyer,
            sale_date=timezone.localdate(self.day(22)),
        )
        sale_with_lines(
            self.farm,
            lines=(("g1", "5.0", 18500),),
            lot=lot,
            buyer=buyer,
            sale_date=timezone.localdate(self.day(23)),
            voided=True,
        )
        return lot
