from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import HarvestFactory, characterized_plot
from apps.lots.tests.factories import LotFactory
from apps.producers.tests.factories import ProducerFactory


class Farmstead:
    """Un productor con dos fincas. En A, dos cajones de 600 kg (C-01 y C-02) y un lote recién
    conformado de 500 kg cosechado hace tres días; el capataz trabaja en A."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.farm_a = FarmFactory(producer=self.producer, number=1)
        self.farm_b = FarmFactory(producer=self.producer, number=2)
        self.plot_a = characterized_plot(farm=self.farm_a, area_hectares=Decimal("5.00"))
        self.plot_b = characterized_plot(farm=self.farm_b, area_hectares=Decimal("5.00"))
        self.box = PostharvestFacilityFactory(farm=self.farm_a, name="C-01", capacity_kg=600)
        self.other_box = PostharvestFacilityFactory(farm=self.farm_a, name="C-02", capacity_kg=600)
        self.harvest_day = timezone.localdate() - timedelta(days=3)
        self.lot = self.new_lot(Decimal("500.0"))
        self.owner = make_producer_owner(self.producer)
        self.foreman = grant_role(
            UserFactory(producer=self.producer, farm=self.farm_a), get_system_role(FOREMAN)
        )

    def new_lot(self, weight, plot=None):
        harvest = HarvestFactory(
            plot=plot or self.plot_a, harvest_date=self.harvest_day, green_weight_kg=weight
        )
        return LotFactory(harvest=harvest)

    def start_body(self, lot=None, **overrides):
        body = {
            "lot_id": str((lot or self.lot).pk),
            "facility_id": str(self.box.pk),
            "started_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            "responsible_id": str(self.foreman.pk),
        }
        body.update(overrides)
        return body
