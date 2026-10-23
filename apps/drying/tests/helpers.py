from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory

FERMENTED_HOURS_AGO = 6


def fermented_lot(
    plot,
    *,
    weight=Decimal("820.0"),
    actor=None,
    harvest_day=None,
    hours_ago=FERMENTED_HOURS_AGO,
):
    """Un lote que llega a Fermentado por su cadena de estados, con los eventos que lo dejan
    registrado, como lo haría una fermentación al finalizar. Sus eventos se corren `hours_ago`
    horas atrás: un secado se puede iniciar desde entonces."""
    harvest = HarvestFactory(
        plot=plot,
        harvest_date=harvest_day or timezone.localdate() - timedelta(days=15),
        green_weight_kg=weight,
    )
    lot = LotFactory(harvest=harvest, status=LotStatus.GENERATED)
    lot.advance_status(LotStatus.GENERATED, LotStatus.FERMENTING, actor=actor)
    lot.advance_status(LotStatus.FERMENTING, LotStatus.FERMENTED, actor=actor)
    lot.audit_events.update(occurred_at=timezone.now() - timedelta(hours=hours_ago))
    return lot


class Farmstead:
    """Un productor con dos fincas. En A, dos marquesinas de 800 kg (M-01 y M-02) y un lote
    Fermentado de 820 kg; el capataz trabaja en A."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm_a = FarmFactory(producer=self.producer, number=1)
        self.farm_b = FarmFactory(producer=self.producer, number=2)
        self.plot_a = characterized_plot(farm=self.farm_a, area_hectares=Decimal("5.00"))
        self.plot_b = characterized_plot(farm=self.farm_b, area_hectares=Decimal("5.00"))
        self.dryer = self.new_dryer("M-01")
        self.other_dryer = self.new_dryer("M-02")
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm_a), get_system_role(FOREMAN)
        )
        self.lot = fermented_lot(self.plot_a, actor=self.owner)

    def new_dryer(self, name, farm=None, **fields):
        return PostharvestFacilityFactory(
            farm=farm or self.farm_a,
            name=name,
            facility_type="solar_dryer",
            capacity_kg=Decimal("800"),
            **fields,
        )

    def start_body(self, lot=None, **overrides):
        body = {
            "lot_id": str((lot or self.lot).pk),
            "facility_id": str(self.dryer.pk),
            "started_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            "entry_moisture_pct": "58.0",
            "responsible_id": str(self.foreman.pk),
        }
        body.update(overrides)
        return body
