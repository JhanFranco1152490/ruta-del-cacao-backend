from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.drying.models import DryingLogEntry, DryingProcess
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory


class DryingProcessFactory(DjangoModelFactory):
    """Un secado en curso desde hace 52 horas, en una marquesina de la finca del lote. No ocupa la
    marquesina ni avanza el lote por los servicios: para eso están los servicios."""

    class Meta:
        model = DryingProcess

    lot = factory.SubFactory(LotFactory, status=LotStatus.DRYING)
    facility = factory.SubFactory(
        PostharvestFacilityFactory,
        farm=factory.SelfAttribute("..lot.harvest.plot.farm"),
        facility_type="solar_dryer",
        name=factory.Sequence(lambda n: f"M-{n:02d}"),
    )
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=52))
    entry_moisture_pct = Decimal("58.0")
    responsible = factory.SubFactory(
        UserFactory, producer=factory.SelfAttribute("..lot.harvest.plot.farm.producer")
    )
    created_by = factory.SelfAttribute("responsible")


class DryingLogEntryFactory(DjangoModelFactory):
    """La bitácora del día `day` del secado, medida tres horas después de la hora de inicio de ese
    día. La fecha y el número de día van de acuerdo, como los deja el servicio."""

    class Meta:
        model = DryingLogEntry

    class Params:
        day = 1

    process = factory.SubFactory(DryingProcessFactory)
    measured_at = factory.LazyAttribute(
        lambda entry: entry.process.started_at + timedelta(days=entry.day - 1, hours=3)
    )
    log_date = factory.LazyAttribute(lambda entry: timezone.localdate(entry.measured_at))
    day_number = factory.SelfAttribute("day")
    moisture_pct = Decimal("45.0")
    sun_hours = Decimal("3.0")
    turn_count = 2
    turn_frequency_hours = Decimal("1.5")
    weather = "sunny"
    recorded_by = factory.SelfAttribute("process.responsible")
