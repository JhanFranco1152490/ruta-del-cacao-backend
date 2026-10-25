from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.facilities.tests.factories import PostharvestFacilityFactory
from apps.fermentation.models import FermentationProcess, FermentationTurn
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory


class FermentationProcessFactory(DjangoModelFactory):
    """Una fermentación en curso desde hace 52 horas, en un cajón de la finca del lote. No ocupa el
    cajón ni avanza el lote por los servicios: para eso están los servicios."""

    class Meta:
        model = FermentationProcess

    lot = factory.SubFactory(LotFactory, status=LotStatus.FERMENTING)
    facility = factory.SubFactory(
        PostharvestFacilityFactory, farm=factory.SelfAttribute("..lot.harvest.plot.farm")
    )
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=52))
    responsible = factory.SubFactory(
        UserFactory, producer=factory.SelfAttribute("..lot.harvest.plot.farm.producer")
    )
    created_by = factory.SelfAttribute("responsible")


class FermentationTurnFactory(DjangoModelFactory):
    """Un volteo una hora después del anterior de la misma fábrica, contado desde el inicio."""

    class Meta:
        model = FermentationTurn

    process = factory.SubFactory(FermentationProcessFactory)
    turned_at = factory.LazyAttributeSequence(
        lambda turn, n: turn.process.started_at.replace(second=0, microsecond=0)
        + timedelta(hours=n + 1)
    )
    temperature_c = Decimal("45.0")
    ph = Decimal("4.90")
    recorded_by = factory.SelfAttribute("process.responsible")
