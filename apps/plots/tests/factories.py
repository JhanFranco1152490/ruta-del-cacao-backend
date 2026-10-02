from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.common.text import normalize_name
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot


class PlotFactory(DjangoModelFactory):
    class Meta:
        model = Plot

    farm = factory.SubFactory(FarmFactory)
    code = factory.Sequence(lambda n: f"P-{n:02d}")
    code_normalized = factory.LazyAttribute(lambda plot: normalize_name(plot.code))
    area_hectares = Decimal("1.00")
