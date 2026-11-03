from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.system_roles import QUALITY_MANAGER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.drying.tests.factories import DryingProcessFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory
from apps.quality.choices import DiscardReason

from .factories import LotClassificationFactory, LotDiscardFactory, QualityEvaluationFactory

DRY_WEIGHT = Decimal("313.2")


def dried_lot(
    plot, *, status=LotStatus.DRIED, dry_weight=DRY_WEIGHT, days_ago=2, harvest_date=None
):
    """Un lote con su secado terminado hace `days_ago` días, con su peso seco. Queda en `status`
    sin pasar por los servicios: las pruebas de cada paso de calidad lo avanzan ellas."""
    harvest = HarvestFactory(
        plot=plot, harvest_date=harvest_date or timezone.localdate() - timedelta(days=20)
    )
    lot = LotFactory(harvest=harvest, status=status)
    ended_at = timezone.now() - timedelta(days=days_ago)
    DryingProcessFactory(
        lot=lot,
        started_at=ended_at - timedelta(hours=116),
        ended_at=ended_at,
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=dry_weight,
        yield_pct=Decimal("38.2"),
        total_sun_hours=Decimal("31.5"),
    )
    return lot


def evaluated(lot, by, *, hours_ago=1):
    return QualityEvaluationFactory(
        lot=lot, evaluated_by=by, evaluated_at=timezone.now() - timedelta(hours=hours_ago)
    )


def classified(lot, by, *, hours_ago=1):
    evaluated(lot, by, hours_ago=hours_ago + 1)
    return LotClassificationFactory(
        lot=lot,
        g1_kg=Decimal("250.0"),
        g2_kg=Decimal("55.2"),
        discard_kg=Decimal("8.0"),
        discard_reason=DiscardReason.MOLD,
        classified_by=by,
        classified_at=timezone.now() - timedelta(hours=hours_ago),
    )


def discarded(lot, by, *, hours_ago=1):
    evaluated(lot, by, hours_ago=hours_ago + 1)
    return LotDiscardFactory(
        lot=lot, discarded_by=by, discarded_at=timezone.now() - timedelta(hours=hours_ago)
    )


class QualityEstate:
    """Un productor con dos fincas. En A: un lote todavía en secado (no entra a calidad), dos Seco
    (el más antiguo se secó hace cinco días), uno Evaluado, uno Clasificado y uno Descartado. En
    B: uno Seco. El Encargado de calidad trabaja en A."""

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

        drying = HarvestFactory(plot=self.plot_a)
        self.drying = LotFactory(harvest=drying, status=LotStatus.DRYING)
        DryingProcessFactory(lot=self.drying)
        self.dried_old = dried_lot(self.plot_a, days_ago=5)
        self.dried_new = dried_lot(self.plot_a, days_ago=1)
        self.evaluated = dried_lot(self.plot_a, status=LotStatus.EVALUATED)
        evaluated(self.evaluated, self.inspector)
        self.classified = dried_lot(self.plot_a, status=LotStatus.CLASSIFIED)
        classified(self.classified, self.inspector, hours_ago=3)
        self.discarded = dried_lot(self.plot_a, status=LotStatus.DISCARDED)
        discarded(self.discarded, self.inspector, hours_ago=2)
        self.dried_b = dried_lot(self.plot_b, days_ago=3)
