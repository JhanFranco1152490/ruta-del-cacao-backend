from datetime import date

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity
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
