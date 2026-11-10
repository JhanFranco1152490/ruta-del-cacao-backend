from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.system_roles import QUALITY_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.choices import LotStatus
from apps.producers.tests.factories import ProducerFactory
from apps.quality.tests.factories import LotClassificationFactory, QualityEvaluationFactory
from apps.quality.tests.helpers import dried_lot

from .factories import StockBalanceFactory, StockEntryFactory, WarehouseFactory

# La clasificación se hizo hace tres días: así "hoy" y "anteayer" caen a un lado y otro de su fecha
# sin depender de la hora a la que corra la prueba.
CLASSIFIED_DAYS_AGO = 3


def classified_lot(
    plot, *, g1="250.0", g2="55.2", status=LotStatus.CLASSIFIED, by=None, harvest_date=None
):
    """Un lote Clasificado con los kilos de G1 y G2 dados. Sin pasar por los servicios."""
    lot = dried_lot(plot, status=status, harvest_date=harvest_date)
    classified_at = timezone.now() - timedelta(days=CLASSIFIED_DAYS_AGO)
    evaluator = by or UserFactory(producer=plot.farm.producer)
    QualityEvaluationFactory(lot=lot, evaluated_by=evaluator, evaluated_at=classified_at)
    LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal(g1),
        g2_kg=Decimal(g2),
        discard_kg=Decimal("0.0"),
        classified_by=evaluator,
        classified_at=classified_at,
    )
    return lot


def stored_lot(
    plot, warehouse, *, g1="250.0", g2="55.2", location="Estante 3", by=None, harvest_date=None
):
    """Un lote En bodega con su ingreso y sus existencias completas, sin los servicios."""
    lot = classified_lot(
        plot, g1=g1, g2=g2, status=LotStatus.IN_WAREHOUSE, by=by, harvest_date=harvest_date
    )
    entry = StockEntryFactory(
        lot=lot,
        warehouse=warehouse,
        location=location,
        g1_kg=Decimal(g1),
        g2_kg=Decimal(g2),
        entry_date=timezone.localdate() - timedelta(days=1),
        entered_by=by or lot.created_by,
    )
    for grade, kilos in (("g1", g1), ("g2", g2)):
        if Decimal(kilos) > 0:
            StockBalanceFactory(
                lot=lot,
                grade=grade,
                quantity_kg=Decimal(kilos),
                warehouse=warehouse,
                location=location,
            )
    return lot, entry


class WarehouseEstate:
    """Un productor con dos fincas, cada una con su bodega. En A: un lote Clasificado, uno con G2
    en 0, uno sin kilos que ingresar y uno En bodega. En B: un Clasificado. El Encargado de calidad
    trabaja en A."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm_a = FarmFactory(producer=self.producer, number=1)
        self.farm_b = FarmFactory(producer=self.producer, number=2)
        self.plot_a = characterized_plot(farm=self.farm_a, area_hectares=Decimal("5.00"))
        self.plot_b = characterized_plot(farm=self.farm_b, area_hectares=Decimal("5.00"))
        self.owner = make_producer_owner(self.producer)
        self.inspector = grant_role(
            UserFactory(producer=self.producer, farm=self.farm_a, first_name="Ana"),
            get_system_role(QUALITY_MANAGER),
        )
        self.warehouse_a = WarehouseFactory(
            farm=self.farm_a, name="Bodega A", name_normalized="bodegaa"
        )
        self.warehouse_b = WarehouseFactory(
            farm=self.farm_b, name="Bodega B", name_normalized="bodegab"
        )

        self.classified = classified_lot(self.plot_a)
        self.classified_g1_only = classified_lot(self.plot_a, g1="300.0", g2="0.0")
        self.classified_empty = classified_lot(self.plot_a, g1="0.0", g2="0.0")
        self.stored, self.entry = stored_lot(self.plot_a, self.warehouse_a, by=self.inspector)
        self.classified_b = classified_lot(self.plot_b)
