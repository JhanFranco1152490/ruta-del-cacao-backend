from datetime import date
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.warehouse.models import StockBalance, StockEntry, StockExit, Warehouse

_same_producer = factory.SelfAttribute("..lot.harvest.plot.farm.producer")


class WarehouseFactory(DjangoModelFactory):
    class Meta:
        model = Warehouse

    farm = factory.SubFactory(FarmFactory)
    name = factory.Sequence(lambda n: f"Bodega {n:03d}")
    name_normalized = factory.LazyAttribute(
        lambda warehouse: warehouse.name.lower().replace(" ", "")
    )


class StockEntryFactory(DjangoModelFactory):
    """El ingreso de un lote En bodega. No crea las existencias ni avanza el lote: para eso está el
    servicio."""

    class Meta:
        model = StockEntry

    lot = factory.SubFactory(LotFactory, status=LotStatus.IN_WAREHOUSE)
    warehouse = factory.SubFactory(
        WarehouseFactory, farm=factory.SelfAttribute("..lot.harvest.plot.farm")
    )
    location = "Estante 3"
    entry_date = date(2026, 10, 30)
    g1_kg = Decimal("250.0")
    g2_kg = Decimal("55.2")
    entered_by = factory.SubFactory(UserFactory, producer=_same_producer)
    entered_at = factory.LazyFunction(timezone.now)


class StockBalanceFactory(DjangoModelFactory):
    class Meta:
        model = StockBalance

    lot = factory.SubFactory(LotFactory, status=LotStatus.IN_WAREHOUSE)
    grade = "g1"
    quantity_kg = Decimal("250.0")
    warehouse = factory.SubFactory(
        WarehouseFactory, farm=factory.SelfAttribute("..lot.harvest.plot.farm")
    )
    location = "Estante 3"


class StockExitFactory(DjangoModelFactory):
    class Meta:
        model = StockExit

    lot = factory.SubFactory(LotFactory, status=LotStatus.IN_WAREHOUSE)
    grade = "g1"
    quantity_kg = Decimal("5.0")
    exit_date = date(2026, 10, 31)
    reason = "sample"
    created_by = factory.SubFactory(UserFactory, producer=_same_producer)
    created_at = factory.LazyFunction(timezone.now)
