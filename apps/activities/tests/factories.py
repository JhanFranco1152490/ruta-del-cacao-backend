from datetime import date
from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity, AgriculturalActivityInput
from apps.inputs.models import InputMovement
from apps.inputs.tests.factories import AgriculturalInputFactory, InputMovementFactory
from apps.plots.tests.factories import PlotFactory


class AgriculturalActivityFactory(DjangoModelFactory):
    class Meta:
        model = AgriculturalActivity

    plot = factory.SubFactory(PlotFactory)
    activity_type = ActivityType.PRUNING
    scheduled_date = factory.LazyFunction(date.today)
    # El responsable es siempre una cuenta del mismo productor de la parcela.
    assignee = factory.SubFactory(
        UserFactory, producer=factory.SelfAttribute("..plot.farm.producer")
    )
    status = ActivityStatus.SCHEDULED


def done_activity(**kwargs) -> AgriculturalActivity:
    return AgriculturalActivityFactory(
        status=ActivityStatus.DONE,
        done_date=date.today(),
        completed_at=timezone.now(),
        **kwargs,
    )


class AgriculturalActivityInputFactory(DjangoModelFactory):
    """Un insumo usado en una actividad realizada, con su salida del inventario de la finca."""

    class Meta:
        model = AgriculturalActivityInput

    activity = factory.LazyFunction(done_activity)
    input = factory.LazyAttribute(
        lambda used: AgriculturalInputFactory(producer=used.activity.plot.farm.producer)
    )
    quantity = Decimal("2")
    stock_movement = factory.LazyAttribute(
        lambda used: InputMovementFactory(
            input=used.input,
            farm=used.activity.plot.farm,
            kind=InputMovement.Kind.CONSUMPTION,
            quantity=-used.quantity,
        )
    )
