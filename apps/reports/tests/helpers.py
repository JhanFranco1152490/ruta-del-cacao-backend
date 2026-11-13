"""Datos de prueba de los reportes: un productor con dos fincas y datos en cada etapa, armados con
las fábricas de cada app y sin pasar por sus servicios."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.accounts.tests.role_helpers import make_delegate, make_producer_owner
from apps.drying.tests.factories import DryingProcessFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory
from apps.reports.request_serializers import ProducerReportQuerySerializer
from apps.reports.services import producer_report

PERIOD = {"from": "2026-01-01", "to": "2026-03-31"}
BOGOTA = ZoneInfo("America/Bogota")
REPORTS = "reports.view_producer_reports"


def at(*moment):
    return datetime(*moment, tzinfo=BOGOTA)


def generate(actor, **query):
    serializer = ProducerReportQuerySerializer(data=query)
    serializer.is_valid(raise_exception=True)
    return producer_report(actor, serializer.validated_data)


def dry(lot, kg, yield_pct="35.0"):
    return DryingProcessFactory(
        lot=lot,
        ended_at=timezone.now(),
        final_moisture_pct=Decimal("7.0"),
        dry_weight_kg=Decimal(kg),
        yield_pct=Decimal(yield_pct),
        total_sun_hours=Decimal("40.0"),
    )


def harvest(plot, day, kg, **fields):
    return HarvestFactory(plot=plot, harvest_date=day, green_weight_kg=Decimal(kg), **fields)


def lot_of(plot, day=date(2026, 2, 1), kg="100.0", status=LotStatus.GENERATED):
    return LotFactory(harvest=harvest(plot, day, kg), status=status)


class Estate:
    """Un productor con La Esperanza (F01, con El Río y La Loma) y El Mirador (F02, con Alto), y
    otro productor con su propia finca."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.owner = make_producer_owner(self.producer)
        self.esperanza = FarmFactory(producer=self.producer, number=1, name="La Esperanza")
        self.mirador = FarmFactory(producer=self.producer, number=2, name="El Mirador")
        self.rio = characterized_plot(farm=self.esperanza, name="El Río")
        self.loma = characterized_plot(farm=self.esperanza, name="La Loma")
        self.alto = characterized_plot(farm=self.mirador, name="Alto")
        self.other_farm = FarmFactory()
        self.other_plot = characterized_plot(farm=self.other_farm)

    def employee(self, *permissions, farm=None):
        return make_delegate(self.producer, [REPORTS, *permissions], farm=farm)
